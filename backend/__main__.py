import argparse
import json
import multiprocessing
import os
import runpy
import shutil
import socket
import sys
from pathlib import Path


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--legacy', choices=['cleaner', 'consolidator'])
    args = parser.parse_args()
    if args.legacy:
        root = Path(__file__).resolve().parents[1]
        source = root / 'legacy' / args.legacy
        mirror = Path(args.data_dir) / 'legacy' / args.legacy
        mirror.mkdir(parents=True, exist_ok=True)
        # Refresh code/assets only; preserve user-created settings, databases and logs.
        for path in source.rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.ico', '.md', '.txt'):
                target = mirror / path.relative_to(source); target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        os.chdir(mirror)
        script = mirror / ('main.py' if args.legacy == 'cleaner' else 'src/main.py')
        sys.path.insert(0, str(script.parent))
        sys.argv = [str(script)]
        if args.legacy == 'cleaner':
            runpy.run_path(str(script), run_name='__main__')
        else:
            sys.path.insert(0, str(mirror))
            from src.ui import main_window
            main_window.APP_DATA_DIR = mirror / 'data'
            main_window.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            from src import main as legacy_main
            sys.exit(legacy_main.main())
        return
    token = os.environ.get('LIBRARY_MANAGER_TOKEN', '')
    import uvicorn
    from .api import create_app
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('127.0.0.1', args.port))
    port = server_socket.getsockname()[1]
    app = create_app(Path(args.data_dir), token, ready=lambda: print(json.dumps({'ready': True, 'port': port}), flush=True))
    uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)).run(sockets=[server_socket])


if __name__ == '__main__': main()
