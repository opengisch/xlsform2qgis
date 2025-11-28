# xlsform2qgis - library to convert XLSForms to QGIS project files

A library used to generate a valid QGIS project out of a given XLSForm file.

## Usage

You can use the library by simply importing:

```python

from xlsform2qgis.xlsforms import XLSFormConverter

converter = XLSFormConverter("input_xlsform.xls")
converter.convert("output_qgis_directory")
```


## Development

```
    git clone git@github.com:suricactus/xlsform2qgis.git
```

This repository uses the [pre-commit](https://pre-commit.com) project.

```
    pre-commit install
```

This repository uses the [poetry](https://python-poetry.org) project.

```
    poetry install
```


## Debugging

If you are using VS Code and want to debug test and debug the project, run:

```
    poetry run python3 -m debugpy --listen 5678 --wait-for-client ./src/xlsform2qgis/xlsforms.py ./output/
```
