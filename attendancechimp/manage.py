#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendancechimp.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    # Include app when generating migrations without an app name.
    if sys.argv[1:] == ["makemigrations"]:
        sys.argv.append("app")
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
