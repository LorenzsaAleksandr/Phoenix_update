import os
import asyncio
from loguru import logger
from playwright.async_api import async_playwright
from phoenix import PhoenixTrade
from restore_wallet import restore_wallet
from wallets import WALLETS
import settings
import utils

# Путь к расширению
user_profile = os.getenv("USERPROFILE")
extension_path = os.path.join(
    user_profile,
    "AppData",
    "Local",
    "Google",
    "Chrome",
    "User Data",
    "Default",
    "Extensions",
    "aflkmfhebedbjioipglgcbcmnbpgliof",
    "0.10.111_0"
)


async def process_wallet(wallet):
    """Обрабатывает конкретный кошелек."""
    logger.info(f"{wallet.address} | Starting wallet processing...")

    # Путь к профилю
    user_data_dir = os.path.join("profiles", wallet.address)
    logger.info(f"Profile path: {os.path.abspath(user_data_dir)}")

    # Проверка существования профиля
    profile_exists = os.path.exists(user_data_dir)
    if profile_exists:
        logger.info(f"{wallet.address} | Profile exists. Using existing profile.")
    else:
        logger.info(f"{wallet.address} | Profile does not exist. Creating new profile.")

    async with async_playwright() as p:
        # Настройка прокси (если указано)
        proxy = None
        if settings.proxy:
            proxy = await utils.format_proxy(settings.proxy)

        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=settings.headless,
            proxy=proxy,
            locale="en-US",
            slow_mo=settings.slow_mo,
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--no-sandbox",
            ],
        )

        try:
            trade = PhoenixTrade(browser, wallet)

            # Логика при отсутствии профиля
            if not profile_exists:
                logger.info(f"{wallet.address} | Profile not found. Restoring wallet...")
                restored = await restore_wallet(browser, wallet)
                if not restored:
                    logger.error(f"{wallet.address} | Wallet restore failed. Skipping.")
                    return

                connected = await trade.connect_wallet()
                if not connected:
                    logger.warning(f"{wallet.address} | Wallet connection failed. Skipping.")
                    return

            # Если профиль существует, разблокируем кошелек
            else:
                unlocked = await trade.unlock_wallet_if_needed()
                if not unlocked:
                    logger.error(f"{wallet.address} | Failed to unlock wallet. Skipping.")
                    return

            # Устанавливаем настройки (Fast) перед продажей
            if settings.fast:
                await trade.set_fast_transactions()

            # Продажа SOL
            sold_sol = await trade.sell_token("SOL", amount=settings.sol_to_sell)
            if not sold_sol:
                logger.info(f"{wallet.address} | Skipping USDC sale as SOL sale was not performed.")
                return

            # Продажа USDC
            await trade.sell_token("USDC", amount=settings.usdc_to_sell)

        except Exception as e:
            logger.error(f"{wallet.address} | Error during processing: {e}")
        finally:
            await browser.close()

    logger.info(f"{wallet.address} | Wallet processing completed.")


async def main():
    """Обработка всех кошельков."""
    tasks = [process_wallet(wallet) for wallet in WALLETS]
    await asyncio.gather(*tasks)
    logger.info("All wallets processed.")


if __name__ == "__main__":
    asyncio.run(main())
