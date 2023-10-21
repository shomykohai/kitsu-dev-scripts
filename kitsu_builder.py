import argparse
import os
import requests
import sys
import subprocess
from colorama import Fore, Style
from getpass import getuser
from ruamel import yaml
from shutil import which
from tqdm import tqdm
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
    tools_parser.add_argument("--add-flag", '-ff', type=str, help="Enable a flag from Flipper.")
    tools_parser.add_argument("--seed", '-s', action="store_true", help="Seed the database.")
    tools_parser.add_argument("--create-user", '-c', type=str, help="Create a user account with 'test' as password. Use only for if registrations don't work.")



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
    if hasattr(args, 'add_flag'):
        if args.add_flag is not None:
            enable_flipper_flag(args.add_flag, args.dev_path)
    if hasattr(args, 'create_user'):
        if args.create_user is not None:
            create_account(args.create_user, args.dev_path)
    if hasattr(args, 'seed'):
        if args.seed is True:
            seed_database(args.dev_path)


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
    query = f"UPDATE users SET permissions=7, title='Staff' WHERE slug='{user}';"
    
    command = f""
    psql = ["docker", "compose", "exec", "-T", "-i", "postgres", "psql", "--username=kitsu_development", "--host=postgres", "-d", "kitsu_development", "--command", query]
    
    # Run the command in the docker container
    
    docker_comp = subprocess.Popen(psql, cwd=dev_env)
    docker_comp.wait()

    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Command executed. If you see {Fore.CYAN}\"UPDATE 1\"{Fore.GREEN}, you now have the POWERS!{Style.RESET_ALL}")


def enable_flipper_flag(flag: str, dev_env: str) -> None:
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Enabling {flag} flag!{Style.RESET_ALL}")
    rails_console = subprocess.Popen(['bin/rails', 'runner', f'Flipper[:{flag}].enable'], cwd=dev_env)
    rails_console.wait()


def create_account(username: str, dev_env: str) -> None:
    headers = {"Content-Type":"application/vnd.api+json"}
    payload = {
    "data": {
        "attributes": {
        "email": f"{username}@kitsu.dev",
        "name": username,
        "password": "test",
        "slug": username
        },
        "type": "users"
        }
    }
    req = requests.post("http://kitsu.localhost:42069/api/edge/users", json=payload, headers=headers)
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Created user \"{username}\"!{Style.RESET_ALL}")


def seed_database(dev_env: str) -> None:
    KITSU_DB_DUMP = "https://f002.backblazeb2.com/file/kitsu-dumps/latest.sql.gz"
    
    # Since bin/seed download a .gz file, it should first extract the db dump, but
    # For some reason the downloaded file is just a plain SQL file, so we must
    # Import it using psql
    KITSU_TOOLS_DIR = os.path.abspath(dev_env)
    
    # We first download the db dump
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.CYAN}Downloading the DB dump, please wait for the download to complete and {Fore.RED}do not{Fore.CYAN} interrupt the process.{Style.RESET_ALL}")
    # Code from https://stackoverflow.com/questions/56795227/how-do-i-make-progress-bar-while-downloading-file-in-python
    with requests.get(KITSU_DB_DUMP, stream=True) as r:
        with open(f"{KITSU_TOOLS_DIR}/anime.sql", 'wb') as f:
            pbar = tqdm(total=int(r.headers['Content-Length']))
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Download completed! Now we'll import it, please wait..{Style.RESET_ALL}\n")
    
    # And import it
    # Instead of using the provided bin/seed, we will directly call docker compose exec 
    # So we don't get "the input device is not a TTY" error message!
    
    # Before seeding we drop the schema manually
    dockercommand = "docker compose exec -T -i postgres psql --username=kitsu_development --host=postgres -d kitsu_development --command"
    dockercommand = dockercommand.split()
    dockercommand.append("DROP SCHEMA public CASCADE;CREATE SCHEMA public;") # Append the query as an unique list element

    docker_comp = subprocess.Popen(dockercommand, cwd=KITSU_TOOLS_DIR)
    docker_comp.wait()

    # Use a string since it's faster for me than writing all that stuff into a list 
    # The -T parameter disable TTY, see https://docs.docker.com/engine/reference/commandline/compose_exec/
    # Also we only seed the kitsu_development DB 
    dockercommand = "docker compose exec -T -i postgres psql --username=kitsu_development --host=postgres kitsu_development"
    
    # Open the DB dump as a file and pass it to sdtin
    # Set the cwd to the kitsu-tools one so we're sure that the postgres container is found
    with open(f"{KITSU_TOOLS_DIR}/anime.sql", 'r') as f:
        docker_comp = subprocess.Popen(dockercommand.split(), cwd=KITSU_TOOLS_DIR, stdin=f)
        docker_comp.wait()

    # And run the migrations
    rake = subprocess.Popen([f'{KITSU_TOOLS_DIR}/bin/rake', 'db:migrate'])
    rake.wait()
    rake = subprocess.Popen([f'{KITSU_TOOLS_DIR}/bin/rake', 'chewy:reset']) # Reindex DB
    rake.wait()

    # After importing, we'll delete the DB dump since it's not used anymore and to free up space
    os.remove(f"{KITSU_TOOLS_DIR}/anime.sql")
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Database imported (anime.sql > kitsu_development)!{Style.RESET_ALL}\n")

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
    else: print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Git was found.{Style.RESET_ALL}")

    # Finally check if yarn is installed so that we can build kitsu-web
    if which("yarn") is None:
        sys.exit(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.RED}Yarn is not installed. Please install yarn before running the script{Style.RESET_ALL}")
    else: print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Yarn was found.{Style.RESET_ALL}\n")

    # Now clone the kitsu-tools repo
    gitclone = subprocess.Popen(['git', 'clone', '--depth', '1', "https://github.com/hummingbird-me/kitsu-tools.git", f"{cwd}/kitsu-tools"])
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
        print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Fixed typesense image.{Style.RESET_ALL}\n")

    # Then dump the changes
    with open(f"{cwd}/kitsu-tools/docker-compose.yml", 'w') as f:
        yamlparser.dump(contents, f)
    
    # Clone the server
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Cloning server.{Style.RESET_ALL}\n")
    gitclone = subprocess.Popen(['git', 'clone', "https://github.com/hummingbird-me/kitsu-server.git", f"{cwd}/kitsu-tools/server"])
    gitclone.wait()

    # Then the client with already applied changes
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Cloning client (from {Fore.CYAN}ShomyKohai/kitsu-web@the-future{Fore.GREEN}).{Style.RESET_ALL}\n")
    gitclone = subprocess.Popen(['git', 'clone', '-b', 'the-future', "https://github.com/ShomyKohai/kitsu-web.git", f"{cwd}/kitsu-tools/client"])
    gitclone.wait()

    # Before building the environment, for some reason the kitsu-web won't start until the
    # node-modules folder is generated, so we run yarn install before building with bin/build
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Running yarn on client.{Style.RESET_ALL}\n")
    yarn = subprocess.Popen([f'yarn', 'install'], cwd=f"{cwd}/kitsu-tools/client")
    yarn.wait() 

    # Build the environment!
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Finally we build!.{Style.RESET_ALL}\n")
    docker_comp = subprocess.Popen([f'{cwd}/kitsu-tools/bin/build'])
    docker_comp.wait()

    # And then we start the containers just to be sure
    docker_comp = subprocess.Popen([f'{cwd}/kitsu-tools/bin/start'])
    docker_comp.wait()

    # HACK: We run db:setup on rails to be sure that we don't encounter an issue when running migrations
    rails_console = subprocess.Popen(["bin/rails", "db:setup"], cwd=cwd)  

    # Now we seed the database if the user chose to
    if should_seed: seed_database(cwd)

    # Finally we have the last steps

    # First we enable registrations in the server so it's possible to create an account from the web page
    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Now we enable registrations in the server!{Style.RESET_ALL}")
    enable_flipper_flag("registration", f"{cwd}/kitsu-tools")

    print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.GREEN}Setup completed!{Style.RESET_ALL}")


if __name__ == '__main__':
    # Check if run with root because of some random errors that may occur when dealing with docker
    if getuser() == "root":
        parse_args()
    else:
        print(f"{Fore.YELLOW}Kitsu Builder {Fore.WHITE}> {Fore.RED}Please run the script as root.{Style.RESET_ALL}")

