"""Tests unitaires de app/paths.py."""
import paths


def test_base_dir_is_the_project_root():
    assert (paths.BASE_DIR / "models.json").is_file()
    assert (paths.BASE_DIR / "i18n" / "fr.json").is_file()
    assert (paths.BASE_DIR / "app" / "paths.py").is_file()


def test_base_dir_is_absolute():
    assert paths.BASE_DIR.is_absolute()


def test_app_data_dir_is_under_home():
    # Le conftest redirige HOME vers un dossier temporaire : jamais le vrai dossier personnel
    assert paths.APP_DATA_DIR.name == ".autotranscript"
    assert paths.APP_DATA_DIR.parent == paths.Path.home()
