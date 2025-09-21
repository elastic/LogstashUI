
# TODO: Potentially deprecate this?

import subprocess, signal, atexit, os, sys

from django.core.management.commands.runserver import Command as RunserverCommand
from django.conf import settings

# TODO: Automatically download logstash and setup simulate.conf
class Command(RunserverCommand):
    help = "Run Django dev server and Logstash together."

    def handle(self, *args, **options):
        options['addrport'] = "0.0.0.0:8080"

        BASE_DIR =os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../..")
        )

        logstash_conf = os.path.join(BASE_DIR, "logstash", "config", "simulate.conf")


        try:
            os.remove(os.path.join(BASE_DIR, "logstash", "data", ".lock"))
        except Exception as e:
            print("Did not remove data lock files, ", e)

        try:
            os.remove(os.path.join(BASE_DIR, "logstash", "config", ".lock"))
        except Exception as e:
            print("Did not remove config lock files, ", e)

        if os.name == "nt":  # Windows
            logstash_bin = os.path.join(BASE_DIR, "logstash", "bin", "logstash.bat")

            settings.LOGSTASH_PROC = subprocess.Popen(
                [
                    logstash_bin,
                    "--pipeline.id", "simulate",
                    "-f", logstash_conf,
                    "--config.reload.automatic"
                ],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )
        else:  # Linux / Mac
            logstash_bin = os.path.join(BASE_DIR, "logstash", "bin", "logstash")
            settings.LOGSTASH_PROC = subprocess.Popen(
                [
                    logstash_bin,
                    "-f", logstash_conf,
                    "--pipeline.id", "simulate",
                    "--config.reload.automatic"
                ],
                preexec_fn=os.setsid,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )

        def cleanup():
            try:
                if os.name == "nt":
                    settings.LOGSTASH_PROC.kill()
                else:
                    os.killpg(os.getpgid(settings.LOGSTASH_PROC.pid), signal.SIGTERM)


            except Exception:
                pass

        atexit.register(cleanup)
        signal.signal(signal.SIGINT, cleanup)
        signal.signal(signal.SIGTERM, cleanup)
        # Start Django normally
        super().handle(*args, **options)
