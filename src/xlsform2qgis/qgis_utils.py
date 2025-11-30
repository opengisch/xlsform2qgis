import atexit
import gc
import logging
import os
import tempfile

from qgis.core import QgsApplication, Qgis, QgsProject


logger = logging.getLogger(__name__)


QGISAPP: QgsApplication | None = None


def start_app() -> str:
    """
    Will start a QgsApplication and call all initialization code like
    registering the providers and other infrastructure. It will not load
    any plugins.

    You can always get the reference to a running app by calling `QgsApplication.instance()`.

    The initialization will only happen once, so it is safe to call this method repeatedly.

        Returns
        -------
        str: QGIS app version that was started.
    """
    global QGISAPP

    extra_envvars = os.environ.get("QFIELDCLOUD_EXTRA_ENVVARS", "[]")

    logger.info(f"Available user defined environment variables: {extra_envvars}")

    if QGISAPP is None:
        logger.info(
            f"Starting QGIS app version {Qgis.versionInt()} ({Qgis.devVersion()})..."
        )
        argvb: list[str] = []

        os.environ["QGIS_CUSTOM_CONFIG_PATH"] = tempfile.mkdtemp("", "QGIS_CONFIG")

        # Note: QGIS_PREFIX_PATH is evaluated in QgsApplication -
        # no need to mess with it here.
        gui_flag = False
        QGISAPP = QgsApplication(argvb, gui_flag)

        QGISAPP.initQgis()

        # make sure the app is closed, otherwise the container exists with non-zero
        @atexit.register
        def exitQgis():
            stop_app()

        logger.info("QGIS app started!")

    return Qgis.version()


def stop_app():
    """
    Cleans up and exits QGIS
    """
    global QGISAPP

    # note that if this function is called from @atexit.register, the globals are cleaned up
    if "QGISAPP" not in globals():
        return

    project = QgsProject.instance()

    assert project

    project.clear()

    if QGISAPP is not None:
        logger.info("Stopping QGIS app…")

        # NOTE we force run the GB just to make sure there are no dangling QGIS objects when we delete the QGIS application
        gc.collect()

        QGISAPP.exitQgis()

        del QGISAPP

        logger.info("Deleted QGIS app!")
