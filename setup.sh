#!/bin/sh
cd `dirname $0`

# Create a virtual environment to run our code
VENV_NAME="venv"
PYTHON="$VENV_NAME/bin/python"
ENV_ERROR="This module requires Python >=3.8, pip, and virtualenv to be installed."

if ! python3 -m venv $VENV_NAME >/dev/null 2>&1; then
    echo "Failed to create virtualenv."
    if command -v apt-get >/dev/null; then
        echo "Detected Debian/Ubuntu, attempting to install python3-venv automatically."
        SUDO="sudo"
        if ! command -v $SUDO >/dev/null; then
            SUDO=""
        fi
		if ! apt info python3-venv >/dev/null 2>&1; then
			echo "Package info not found, trying apt update"
			$SUDO apt -qq update >/dev/null
		fi
        $SUDO apt install -qqy python3-venv >/dev/null 2>&1
        if ! python3 -m venv $VENV_NAME >/dev/null 2>&1; then
            echo $ENV_ERROR >&2
            exit 1
        fi
    else
        echo $ENV_ERROR >&2
        exit 1
    fi
fi

# remove -U if viam-sdk should not be upgraded whenever possible
# -qq suppresses extraneous output from pip
echo "Virtualenv found/created. Installing/upgrading Python packages..."

# .installed holds a copy of the requirements.txt the venv was built from, so a
# changed requirements.txt triggers a reinstall. The import check catches a venv
# that was marked installed but is corrupt (e.g. truncated files after a power
# loss or full disk), which would otherwise crash-loop the module forever.
venv_ok() {
    cmp -s requirements.txt .installed &&
        $PYTHON -c "from viam.module.module import Module" >/dev/null 2>&1
}

if ! venv_ok; then
    if [ -f .installed ]; then
        echo "Virtualenv is stale or broken, rebuilding..."
        rm -rf $VENV_NAME .installed
        if ! python3 -m venv $VENV_NAME >/dev/null 2>&1; then
            echo $ENV_ERROR >&2
            exit 1
        fi
    fi
    if ! $PYTHON -m pip install -r requirements.txt -Uqq; then
        exit 1
    fi
    if ! $PYTHON -c "from viam.module.module import Module"; then
        echo "viam-sdk is still not importable after install." >&2
        exit 1
    fi
    cp requirements.txt .installed
fi
