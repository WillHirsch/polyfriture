# Installing Polyfriture

## Binary releases

Get the latest binary releases for Windows, macOS and Linux on the [Releases](https://github.com/WillHirsch/polyfriture/releases) page.

## Running Polyfriture from source on Linux

The following steps can be used to prepare a development environment for Polyfriture on Ubuntu.

Prerequisite: a 64 bits Linux installation (PyQt6 wheels for Linux are only available for 64 bits).

This has been tested in a Virtualbox image for Ubuntu Trusty 16.04 LTS 64 bits from osboxes.org. The following custom settings have been set on the VM: increase video memory, enable 3d acceleration, enable audio input, install guest addition, add user to vboxsf (for file sharing with the host), keyboard layout setup.

1. Install git
```
sudo apt-get update
sudo apt-get install -y git
```

2. Install `portaudio` (used for audio IO in Polyfriture)
```
sudo apt-get install -y libportaudio2
```

3. Install uv (Python package manager)
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

4. Clone the repository
```
git clone https://github.com/WillHirsch/polyfriture.git
cd polyfriture
```

5. Optional: switch to a specific branch
```
git fetch
git checkout origin/<branchName>
```

6. Create a virtual environment and install Polyfriture dependencies (PyQt6, etc.)
```
uv sync
```

7. Run Polyfriture
```
uv run polyfriture
```

## Running Polyfriture from source on Windows

The following steps can be used to prepare a development environment for Polyfriture on Windows.

1. Clone this repo

2. Install *chocolatey* from https://chocolatey.org/install

 2. Install Python and uv. With chocolatey, in an administrator terminal:

```
choco install -y choco\packages.config
```

Watch out for a message indicating that a reboot is necessary.

The next commands do not need to be run in an administrator terminal.

4. Create a virtual environment and install dependencies
```
uv sync
```

`uv sync` handles everything: it creates the virtual environment and installs all dependencies.

5. Run Polyfriture

```
uv run polyfriture
```

## Dependencies

See [pyproject.toml](pyproject.toml)

## UI and resource files

If `settings.ui` or `resource.qrc` are changed, the corresponding python files need to be rebuilt:

```
uv run pyuic6 ui/settings.ui -o polyfriture/ui_settings.py
uv run pyrcc6 resources/friture.qrc -o polyfriture/friture_rc.py
```

## Filters parameters

The filters parameters are precomputed in files called `generated_filters.py`
(IIR coefficients) and `generated_fft.py` (precomputed FIR coefficients and
FFT frequency responses). To rebuild these files, run:

```
uv run python polyfriture/filter_design.py
```

Note: `filter_design.py` requires `scipy` to be installed.
