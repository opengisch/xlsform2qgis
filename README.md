# xlsform2qgis - library to convert XLSForms to QGIS project files

A library used to generate a valid QGIS project out of a given XLSForm file.

## Usage

You can use the library by simply importing:

```python

from xlsform2qgis.converter import XLSFormConverter

converter = XLSFormConverter("input_xlsform.xls")
converter.convert("output_qgis_directory")
```

Or by running from the commandline:

```
uv run xlsform2qgis ./samples/service_rating.xlsx ./output/
```


## Development


1. Clone the repository:

```
git clone git@github.com:suricactus/xlsform2qgis.git
```

2. This repository uses the [pre-commit](https://pre-commit.com) project. Install it on this project.

```
pre-commit install
```

3. This repository uses the [uv](https://docs.astral.sh/uv) project. Create a new environment.

```
uv venv
```

4. Manually add the externally managed `PyQt5` and `qgis` libraries to your environment:

```
ln -s /usr/lib/python3/dist-packages/qgis .venv/lib/python3.12/site-packages/
ln -s /usr/lib/python3/dist-packages/PyQt5 .venv/lib/python3.12/site-packages/
```

5. OPTIONAL Add the `xlsform2qgis` library system wide in all Python scripts.

```
sudo uv pip install --system --break-system-packages --editable .
```


## Debugging

If you are using VS Code and want to debug test and debug the project, run:

```
uv run python3 -m debugpy --listen 5678 --wait-for-client ./src/xlsform2qgis/converter.py ./samples/service_rating.xlsx ./output/
```
