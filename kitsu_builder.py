import argparse
import os
import sys
import subprocess
from colorama import Fore, Style
from urllib import request
from ruamel import yaml
from shutil import which
from typing import (
    Optional
)

def parse_args() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Helper script to build Kitsu!"
    )
    
    subparser = parser.add_subparsers()

    # Set-up the dev env
    setup_parser = subparser.add_parser("setup", help="Setup your dev-environment")
    setup_parser.add_argument('--path', '-p', type=check_valid_folder, help="The path where the dev env will be set-up", required=True)
    setup_parser.add_argument('--seed', '-s', action="store_true", help="If the Database should be seeded")
    
    tools_parser = subparser.add_parser("tools", help="Useful commands that may become handy in any moment! Must already have a dev env before using any of the tools.")
    # Give admin privileges to the user
    tools_parser.add_argument('--dev-path', '-dp', type=str, help="The path where the dev env is located.", required=True)
    tools_parser.add_argument("--gain-super-admin", "-a",
        type=str.lower,
        nargs='?', 
        help="Gain the PRIVILEGES! (Or: Set the given user permissions to those of super-admin); Provide the SLUG of your user with no quotes"
    )
    


    args = parser.parse_args()

    # Checks if the script was called without arguments
    if not vars(args):
        parser.print_help()
        return

    # Call the setup function
    if hasattr(args, "path"):
        if args.path is not None: 
            setup(args.path, args.seed)
            return
    
    # Tools
    if hasattr(args, 'gain_super_admin'):
        if args.gain_super_admin is not None:
            gain_admin_powers(args.gain_super_admin, args.dev_path)
            return

def check_valid_folder(dir: str) -> Optional[str]:
    # First check if the folder exists
    if not os.path.isdir(dir):
        sys.exit(f'The provided directory does not exist: \'{dir}\'')
    
    # Then if it's empty
    if os.listdir(dir):
        sys.exit(f'The directory is not empty: \'{dir}\'')
    
    # Finally return back the path
    return dir


def gain_admin_powers(user: str, dev_env: str) -> None:
    # Define the query
    query = f"UPDATE users SET permissions=7 WHERE slug='{user}';"
    
    command = f""
    psql = ["docker", "compose", "exec", "-T", "-i", "postgres", "psql", "--username=kitsu_development", "--host=postgres", "-d", "kitsu_development", "--command", query]
    
    # Run the command in the docker container
    
    docker_comp = subprocess.Popen(psql, cwd=dev_env)
    docker_comp.wait()

    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Command executed. If you see {Fore.CYAN}\"UPDATE 1\"{Fore.GREEN}, you now have the POWERS!{Style.RESET_ALL}")



def setup(path: str, should_seed: bool = False) -> None:
    cwd = path
    
    # Check if Docker & Docker Compose are installed
    if which("docker") is None:
        sys.exit(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.RED}Docker is not installed. Please install it and run the script again.{Style.RESET_ALL}")
    else: print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Docker was found.{Style.RESET_ALL}")

    if which("docker-compose") is None:
        sys.exit(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.RED}Docker-compose is not installed. Please install it and run the script again.{Style.RESET_ALL}")
    else: print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Docker-compose was found.{Style.RESET_ALL}")
    
    # Also check if git is installed so we can clone the repos
    if which("git") is None:
        sys.exit(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.RED}Cannot continue without a valid git installation. Please install git before running the script{Style.RESET_ALL}")
    else: print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Git was found.{Style.RESET_ALL}\n")

    # Now clone the kitsu-tools repo
    gitclone = subprocess.Popen(['git', 'clone', "https://github.com/hummingbird-me/kitsu-tools.git", f"{cwd}/kitsu-tools"])
    gitclone.wait()

    # Now apply changes to the kitsu-tools docker-compose.yml file to use the correct typesense image
    with open(f"{cwd}/kitsu-tools/docker-compose.yml", 'r') as f:
        yamlparser = yaml.YAML()
        # Preserve the quotes etc.
        yamlparser.preserve_quotes = True

        contents = yamlparser.load(f)

    # Replace only if the typesense image is wrong
    if contents["services"]["typesense"]["image"] == "typesense:0.25.0.rc54":
        contents["services"]["typesense"]["image"] = "typesense/typesense:0.25.0.rc54"

    # Then dump the changes
    with open(f"{cwd}/kitsu-tools/docker-compose.yml", 'w') as f:
        yamlparser.dump(contents, f)
    
    # Clone the server
    gitclone = subprocess.Popen(['git', 'clone', "https://github.com/hummingbird-me/kitsu-server.git", f"{cwd}/kitsu-tools/server"])
    gitclone.wait()

    # Then the client with already applied changes
    gitclone = subprocess.Popen(['git', 'clone', '-b', 'the-future', "https://github.com/ShomyKohai/kitsu-web.git", f"{cwd}/kitsu-tools/client"])
    gitclone.wait()

    # Build the environment!
    docker_comp = subprocess.Popen([f'{cwd}/kitsu-tools/bin/build'])
    docker_comp.wait()

    # And then we start the containers just to be sure
    docker_comp = subprocess.Popen([f'{cwd}/kitsu-tools/bin/start'])
    docker_comp.wait()

    # Now we seed the database if the user chose to
    if should_seed:
        KITSU_DB_DUMP = "https://f002.backblazeb2.com/file/kitsu-dumps/latest.sql.gz"
        
        # Since bin/seed download a .gz file, it should first extract the db dump, but
        # For some reason the downloaded file is just a plain SQL file, so we must
        # Import it using psql
        KITSU_TOOLS_DIR = f"{cwd}/kitsu-tools"
        
        # We first download the db dump
        print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.CYAN}Downloading the DB dump, please wait for the download to complete and {Fore.RED}do not{Fore.CYAN} interrupt the process.{Style.RESET_ALL}")
        request.urlretrieve(KITSU_DB_DUMP, f"{KITSU_TOOLS_DIR}/anime.sql")
        print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Download completed! Now we'll import it, please wait..{Style.RESET_ALL}\n")
        # And import it
        # Instead of using the provided bin/seed, we will directly call docker compose exec 
        # So we don't get "the input device is not a TTY" error message!
        
        # Use a string since it's faster for me than writing all that stuff into a list 
        # The -T parameter disable TTY, see https://docs.docker.com/engine/reference/commandline/compose_exec/
        # Also we only seed the kitsu_development DB 
        dockercommand = "docker compose exec -T -i postgres psql --username=kitsu_development --host=postgres kitsu_development < {KITSU_TOOLS_DIR}/anime.sql"

        # Set the cwd to the kitsu-tools one so we're sure that the postgres container is found
        docker_comp = subprocess.Popen(dockercommand.split(), cwd=KITSU_TOOLS_DIR)
        docker_comp.wait()

        # And run the migrations
        rake = subprocess.Popen([f'{KITSU_TOOLS_DIR}/bin/rake'], 'db:migrate')
        rake.wait()
        rake = subprocess.Popen([f'{KITSU_TOOLS_DIR}/bin/rake'], 'chewy:reset') # Reindex DB
        rake.wait()

        # After importing, we'll delete the DB dump since it's not used anymore and to free up space
        os.remove(f"{KITSU_TOOLS_DIR}/anime.sql")
        print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Database imported (anime.sql > kitsu_development)!{Style.RESET_ALL}\n")

    # Finally we have the last steps

    # First we enable registrations in the server so it's possible to create an account from the web page
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Now we enable registrations in the server!{Style.RESET_ALL}")
    rails_console = subprocess.Popen([f'{cwd}/kitsu-tools/bin/rails', 'runner', '\"Flipper[:registration].enable\"'])

    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Setup completed!{Style.RESET_ALL}")


if __name__ == '__main__':
    parse_args()
