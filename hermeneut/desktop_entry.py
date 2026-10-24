"""Entry point for PyInstaller-packaged desktop sidecar."""
import os
import sys
import uvicorn


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'local-runtime':
        from hermeneut.research.local_runtime import main as local
        local(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'research-command':
        from hermeneut.research.cli import main as research
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        research()
        return
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get('HERMENEUT_PORT', '8000'))
    uvicorn.run(
        'hermeneut.research.api:app' if os.getenv('HERMENEUT_DATABASE_URL') and os.getenv('HERMENEUT_RUNTIME') != 'sqlite' else 'hermeneut.api:app',
        host='127.0.0.1',
        port=port,
        log_level='info',
    )


if __name__ == '__main__':
    main()
