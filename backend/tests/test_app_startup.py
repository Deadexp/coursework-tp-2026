import subprocess
import sys


def test_app_registers_all_tables_for_foreign_keys() -> None:
    """Запускает приложение в чистом интерпретаторе, как это делает uvicorn.

    В тестах conftest сам импортирует все модели, поэтому без отдельного процесса
    не увидеть ситуацию, когда приложение не загрузило модель, на которую ссылается внешний ключ.
    """
    code = (
        "import app.main\n"
        "from app.core.db import Base\n"
        "for table in Base.metadata.tables.values():\n"
        "    for fk in table.foreign_keys:\n"
        "        fk.column\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
