{
  description = "zulip-researcher — recommend research questions from Zulip, publish deep research to Smith Wiki and Bluesky";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.llm-agents.url = "github:numtide/llm-agents.nix";

  outputs = { self, nixpkgs, llm-agents }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});

      mkResearcher = pkgs: pkgs.python3.pkgs.buildPythonApplication {
        pname = "zulip-researcher";
        version = "0.1.0";
        pyproject = true;
        src = ./.;
        nativeBuildInputs = [ pkgs.python3.pkgs.setuptools ];
        propagatedBuildInputs = [ pkgs.python3.pkgs.zulip pkgs.python3.pkgs.requests ];
        doCheck = false;
      };

      # Microsandbox on Apple silicon runs arm64 Linux guests.
      guestSystem = "aarch64-linux";
      guestPkgs = nixpkgs.legacyPackages.${guestSystem};

      # A generic, offline OCI image: interpreter + git + CA certs + the package.
      # No operator setup or secrets are baked in; everything is runtime env.
      # The image bundles omp (from llm-agents.nix) plus git and the package, so the
      # whole researcher runs in one microVM (ADR-0002).
      researcherImage =
        let researcher = mkResearcher guestPkgs;
        in guestPkgs.dockerTools.buildLayeredImage {
          name = "zulip-researcher";
          tag = "latest";
          contents = [ researcher llm-agents.packages.${guestSystem}.omp guestPkgs.git guestPkgs.openssh guestPkgs.bash guestPkgs.coreutils guestPkgs.jq guestPkgs.cacert ];
          config = {
            Entrypoint = [ "zulip-researcher" ];
            Cmd = [ "once" ];
            Env = [
              "SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt"
              "GIT_SSL_CAINFO=/etc/ssl/certs/ca-bundle.crt"
            ];
          };
        };
    in
    {
      packages = forAll (pkgs:
        let
          researcher = mkResearcher pkgs;

          # Debug run: the CLI under `secretspec run`, in Python dev mode.
          debug = pkgs.writeShellApplication {
            name = "zulip-researcher-debug";
            runtimeInputs = [ researcher pkgs.secretspec ];
            text = ''
              export PYTHONDEVMODE=1
              export PYTHONWARNINGS="''${PYTHONWARNINGS:-default}"
              exec secretspec run -- zulip-researcher "''${@:-once}"
            '';
          };

          # Isolated run: the CLI inside a Microsandbox microVM built from the
          # local image. ONLY the listed input env is forwarded; no host mounts,
          # no ambient SSH/git config. Push uses PUSH_TOKEN over HTTPS.
          sandbox = pkgs.writeShellApplication {
            name = "zulip-researcher-sandbox";
            runtimeInputs = [ pkgs.secretspec pkgs.nix pkgs.coreutils pkgs.gzip ];
            text = ''
              # msb is installed outside Nix (e.g. ~/.microsandbox/bin), which may
              # not be on PATH under `nix run`; resolve it from the usual spots.
              msb=$(command -v msb || true)
              for p in "$HOME/.local/bin/msb" "$HOME/.microsandbox/bin/msb"; do
                [ -n "$msb" ] && break
                [ -x "$p" ] && msb="$p"
              done
              if [ -z "$msb" ]; then
                echo "microsandbox (msb) not found (PATH, ~/.local/bin, ~/.microsandbox/bin)" >&2
                exit 127
              fi
              # Resolve secrets once via SecretSpec, then re-enter with them in env.
              if [ -z "''${_RESEARCHER_SECRETSPEC:-}" ]; then
                exec secretspec run -- env _RESEARCHER_SECRETSPEC=1 "$0" "$@"
              fi

              echo "building local image (linux)..." >&2
              tar=$(nix build "${self}#image" --no-link --print-out-paths)
              gunzip -c "$tar" | "$msb" load -q -t zulip-researcher:latest

              # The explicit input surface: secrets + non-secret RESEARCHER_* config.
              secrets=(ZULIP_URL ZULIP_API_KEY ZULIP_API_USERNAME \
                       PREPARE_URL PREPARE_TOKEN PUSH_TOKEN \
                       ANTHROPIC_API_KEY OPENAI_API_KEY OPENAI_BASE_URL \
                       WEB_SEARCH_API_KEY \
                       BLUESKY_ANDYSMITH_APP_PASSWORD BLUESKY_SMITHWIKI_APP_PASSWORD)
              envargs=()
              for k in "''${secrets[@]}"; do
                if [ -n "''${!k:-}" ]; then envargs+=( -e "$k=''${!k}" ); fi
              done
              while IFS='=' read -r k _; do
                case "$k" in RESEARCHER_*) envargs+=( -e "$k=''${!k}" );; esac
              done < <(env)
              # Also forward RESEARCHER_* config from ./.env (plain KEY=value).
              if [ -f .env ]; then
                while IFS= read -r line; do
                  case "$line" in
                    RESEARCHER_*=*) envargs+=( -e "$line" );;
                  esac
                done < .env
              fi
              # Ephemeral in-VM clone dirs unless the caller pinned them.
              printf '%s\n' "''${envargs[@]}" | grep -q 'RESEARCHER_WIKI_CLONE_DIR=' \
                || envargs+=( -e RESEARCHER_WIKI_CLONE_DIR=/tmp/wiki )
              printf '%s\n' "''${envargs[@]}" | grep -q 'RESEARCHER_BLUESKY_CLONE_DIR=' \
                || envargs+=( -e RESEARCHER_BLUESKY_CLONE_DIR=/tmp/bluesky )

              # Long-running `run` needs a PTY or msb buffers guest stdout until
              # exit; fall back to --no-tty when not attached to a terminal.
              tty=(--no-tty); [ -t 1 ] && tty=(-t)
              exec "$msb" run "''${tty[@]}" "''${envargs[@]}" \
                zulip-researcher:latest -- "''${@:-once}"
            '';
          };
        in
        {
          default = researcher;
          image = researcherImage;
          inherit debug sandbox;
        });

      apps = forAll (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.system}.default}/bin/zulip-researcher";
        };
        debug = {
          type = "app";
          program = "${self.packages.${pkgs.system}.debug}/bin/zulip-researcher-debug";
        };
        sandbox = {
          type = "app";
          program = "${self.packages.${pkgs.system}.sandbox}/bin/zulip-researcher-sandbox";
        };
      });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: [ ps.pytest ps.zulip ps.requests ]))
            pkgs.git pkgs.jq pkgs.secretspec
          ];
          shellHook = ''
            echo "zulip-researcher dev shell — python -m zulip_researcher <run|once|show>"
            echo "  nix run .#debug   -- once   # SecretSpec + Python dev mode"
            echo "  nix run .#sandbox -- once   # Microsandbox microVM (local image)"
          '';
        };
      });

      checks = forAll (pkgs: {
        default = pkgs.stdenvNoCC.mkDerivation {
          name = "zulip-researcher-check";
          src = ./.;
          nativeBuildInputs = [
            (pkgs.python3.withPackages (ps: [ ps.pytest ps.zulip ps.requests ]))
            pkgs.git
          ];
          buildPhase = "python -m pytest";
          installPhase = "mkdir -p $out";
        };
      });
    };
}
