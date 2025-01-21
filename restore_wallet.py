from loguru import logger
from playwright.async_api import BrowserContext
from data.models import Wallet
import settings


async def restore_wallet(context: BrowserContext, wallet: Wallet) -> bool:
    for attempt in range(1, settings.attempts_number_restore + 1):
        try:
            logger.info(f'{wallet.address} | Restoring wallet...')
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(f'chrome-extension://aflkmfhebedbjioipglgcbcmnbpgliof/options.html?onboarding=true')

            # Импорт кошелька
            await page.get_by_text('Import Wallet').click()
            await page.get_by_text('Solana').click()
            await page.get_by_text('Import private key').click()
            await page.locator('textarea').fill(wallet.private_key)
            await page.get_by_text('Import').click()

            # Установка пароля
            await page.locator('input[type="password"]').nth(0).fill(settings.extension_password)
            await page.locator('input[type="password"]').nth(1).fill(settings.extension_password)
            await page.locator('input[type="checkbox"]').click()
            await page.get_by_text('Next').click()

            logger.success(f'{wallet.address} | Wallet restored successfully.')
            return True
        except Exception as err:
            logger.error(f'{wallet.address} | Error: {err}')
            if attempt == settings.attempts_number_restore:
                return False
