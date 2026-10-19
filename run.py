import os
import sys

from dotenv import load_dotenv

# .env нужно прочитать ДО импорта приложения: app.config считывает переменные окружения при импорте
load_dotenv()

from app import create_app  # noqa: E402

app = create_app(os.environ.get("FLASK_CONFIG", "development"))

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

if __name__ == "__main__":
    # По умолчанию слушаем только localhost: приложение рассчитано на локальный запуск.
    # Чтобы открыть его в сети, задайте HOST=0.0.0.0 явно (лучше — за reverse-proxy с HTTPS).
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5001))
    debug = bool(app.config.get("DEBUG", False))

    if debug and host not in LOOPBACK_HOSTS:
        # Интерактивный отладчик Werkzeug позволяет выполнять код на сервере. Даже под PIN-кодом
        # его нельзя выставлять в сеть, поэтому при нелокальном HOST отладка принудительно выключается.
        print("ВНИМАНИЕ: HOST=%s — режим отладки отключён (отладчик нельзя выставлять в сеть)." % host,
              file=sys.stderr)
        debug = False

    app.run(host=host, port=port, debug=debug)
