"""Entry point for PyInstaller-packaged desktop sidecar."""
import os
import sys
import uvicorn


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'local-runtime':
        from scriptorium.research.local_runtime import main as local
        local(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'research-command':
        from scriptorium.research.cli import main as research
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        research()
        return
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get('SCRIPTORIUM_PORT', '8000'))
    uvicorn.run(
        'scriptorium.research.api:app' if os.getenv('SCRIPTORIUM_DATABASE_URL') and os.getenv('SCRIPTORIUM_RUNTIME') != 'sqlite' else 'scriptorium.api:app',
        host='127.0.0.1',
        port=port,
        log_level='info',
    )


if __name__ == '__main__':
    main()
