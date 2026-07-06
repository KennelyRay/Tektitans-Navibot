import os
import sys
import traceback
from pathlib import Path

from flask import Flask, Response


BOOT_ERROR = None
PROJECT_ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__)

#region debug-point bootstrap-import
try:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from Bart_Bot import app as flask_app

    app = flask_app
except Exception:
    BOOT_ERROR = traceback.format_exc()

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def boot_error(path):
        debug_body = "\n".join(
            [
                "Vercel bootstrap failed.",
                "",
                f"path={path}",
                f"python={sys.version}",
                f"project_root_exists={PROJECT_ROOT.exists()}",
                f"project_root={PROJECT_ROOT}",
                f"cwd={os.getcwd()}",
                "",
                "traceback:",
                BOOT_ERROR or "No traceback captured.",
            ]
        )
        return Response(debug_body, status=500, mimetype="text/plain")
#endregion
