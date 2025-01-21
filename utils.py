async def format_proxy(proxy: str) -> dict:
    """
    Форматирует строку прокси-сервера в словарь для Playwright.
    Пример входной строки: http://username:password@server:port
    """
    username_password, server_port = proxy.replace('http://', '').split('@')
    username, password = username_password.split(':')
    server, port = server_port.split(':')
    return {
        "server": f"http://{server}:{port}",
        "username": username,
        "password": password,
    }


async def retry_on_failure(coro, max_retries: int, *args, **kwargs):
    """
    Выполняет указанную корутину с повторными попытками при ошибках

    :param coro: корутина для выполнения
    :param max_retries: максимальное количество попыток
    :param args: позиционные аргументы для корутины
    :param kwargs: именованные аргументы для корутины
    :return: результат выполнения корутины
    :raises: Исключение, если корутина не удалась после всех попыток
    """
    for attempt in range(max_retries):
        try:
            return await coro(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
            else:
                print(f"Failed after {max_retries} attempts.")
                raise


