from loguru import logger
from playwright.async_api import BrowserContext, Page, expect
from data.models import Wallet
import settings


class PhoenixTrade:
    def __init__(self, context: BrowserContext, wallet: Wallet):
        self.context = context
        self.wallet = wallet

    async def get_page(self, title_contains: str, url: str = None) -> Page:
        """Открывает или возвращает страницу по названию."""
        for page in self.context.pages:
            if title_contains in await page.title():
                return page
        if url:
            if self.context.pages and self.context.pages[0].url == "about:blank":
                page = self.context.pages[0]
                await page.goto(url)
            else:
                page = await self.context.new_page()
                await page.goto(url)
            return page
        raise ValueError(f"Page with title containing '{title_contains}' not found and no URL provided.")

    @staticmethod
    async def click_if_visible(page: Page, selector: str, description: str = ""):
        """Кликает по элементу, если он видим."""
        try:
            element = page.locator(selector)
            await expect(element).to_be_visible()
            await element.click()
            logger.info(f"Clicked on: {description or selector}")
        except Exception as e:
            logger.warning(f"Failed to click on {description or selector}: {e}")

    async def unlock_wallet_if_needed(self) -> bool:
        """Проверяет и разблокирует кошелек, если он заблокирован."""
        try:
            page = await self.get_page(
                "Backpack", f'chrome-extension://aflkmfhebedbjioipglgcbcmnbpgliof/popup.html'
            )
            unlock_btn = page.get_by_text("Unlock")
            if await unlock_btn.is_visible():
                # Вводим пароль и подтверждаем
                password_field = page.locator('input[type="password"]')
                await password_field.fill(settings.extension_password)
                await unlock_btn.click()
                logger.info(f"{self.wallet.address} | Wallet unlocked successfully.")
                return True
            logger.info(f"{self.wallet.address} | Wallet is already unlocked.")
            return True
        except Exception as e:
            logger.warning(f"{self.wallet.address} | Failed to unlock wallet: {e}")
            return False

    @staticmethod
    async def approve_transaction(page: Page):
        """Подтверждает транзакцию."""
        try:
            unlock_btn = page.get_by_text("Unlock")
            if await unlock_btn.is_visible():
                await unlock_btn.click()
                logger.info("Unlock clicked.")
            approve_btn = page.get_by_text("Approve")
            await expect(approve_btn).to_be_visible()
            await approve_btn.click()
            logger.info("Transaction approved.")
        except Exception as e:
            logger.warning(f"Transaction approval failed: {e}")

    async def connect_wallet(self, max_retries: int = 10) -> bool:
        """Подключает кошелек к Phoenix."""
        logger.info(f'{self.wallet.address} | Connecting wallet...')
        for attempt in range(1, max_retries + 1):
            try:
                phoenix_page = await self.get_page("Phoenix", settings.phoenix_url)

                # Ждем загрузки страницы
                await phoenix_page.wait_for_load_state("networkidle")

                connect_wallet_btn = phoenix_page.get_by_role("button", name="Connect Wallet")
                if await connect_wallet_btn.is_visible():
                    await connect_wallet_btn.click()
                    logger.info(f'{self.wallet.address} | Clicked "Connect Wallet".')

                    await self.click_if_visible(phoenix_page, 'text="Backpack"', "Backpack Option")

                    backpack_page = await self.get_page(
                        "Backpack",
                        f'chrome-extension://aflkmfhebedbjioipglgcbcmnbpgliof/options.html?onboarding=true'
                    )
                    unlock_btn = backpack_page.get_by_text("Unlock")
                    if await unlock_btn.is_visible():
                        await unlock_btn.click()
                        logger.info(f"{self.wallet.address} | Wallet unlocked.")
                    else:
                        logger.warning(f"{self.wallet.address} | Unlock button not visible.")

                    await self.click_if_visible(backpack_page, 'text="Approve"', "Approve Button")
                    logger.success(f'{self.wallet.address} | Wallet connected successfully.')
                    return True
                else:
                    logger.warning(f"{self.wallet.address} | Connect Wallet button not visible.")
                    return False
            except Exception as e:
                logger.error(f'{self.wallet.address} | Connection attempt {attempt} failed: {e}')
        return False

    async def sell_token(self, token_name: str, amount: float = None, fast: bool = settings.fast,
                         max_retries: int = 10) -> bool:
        """Продает указанный токен. Возвращает True, если продажа выполнена, иначе False."""
        logger.info(f'{self.wallet.address} | Selling {token_name}...')
        phoenix_page = await self.get_page("Phoenix", settings.phoenix_url)

        for attempt in range(1, max_retries + 1):
            try:
                await phoenix_page.bring_to_front()

                # Включаем быстрые транзакции, если требуется
                if fast:
                    await self.click_if_visible(phoenix_page, 'svg.settings-icon', "Settings")
                    await self.click_if_visible(phoenix_page, 'text="Fast"', "Fast Transactions")
                    close_btn = phoenix_page.locator('ion-icon[icon="close"]').nth(1)
                    await close_btn.click()

                # Проверяем баланс
                await phoenix_page.wait_for_load_state("networkidle")
                check_amount = phoenix_page.get_by_text("Max:")
                if await check_amount.is_visible():
                    text = await check_amount.text_content()
                    balance = float(text.split("Max: ")[1].strip()) if "Max:" in text else 0
                    logger.info(f'{self.wallet.address} | Balance for {token_name}: {balance}')
                    if balance == 0:
                        logger.warning(f'{self.wallet.address} | Balance is 0 for {token_name}. Skipping wallet.')
                        return False  # Прекращаем выполнение функции, если баланс равен 0

                    input_amount = min(amount or balance, balance)
                else:
                    logger.warning(
                        f'{self.wallet.address} | Balance locator is not visible for {token_name}. Skipping wallet.')
                    return False  # Прекращаем выполнение функции, если баланс не виден

                # Вводим сумму
                await phoenix_page.locator('input[value=""]').nth(2).type(f'{input_amount}')

                # Проверка кнопки Place Order
                place_order_btn = phoenix_page.locator('button.sc-eqUAAy.sc-fqkvVR.sc-iGgWBj.clpFdu.ecLVOp.dWZrWT')
                btn_text = await place_order_btn.text_content()
                if btn_text in [
                    "Enter an amount", "Insufficient SOL balance", "Insufficient USDC balance",
                    "Insufficient liquidity", "Insufficient size", "Country not supported"
                ]:
                    logger.warning(f'{self.wallet.address} | Place Order Button Not Working: {btn_text}')
                    await phoenix_page.reload()
                    continue

                # Клик по кнопке Place Order
                await place_order_btn.click()

                # Подтверждение транзакции
                await self.approve_transaction(phoenix_page)

                # Проверка статуса транзакции
                status = phoenix_page.locator('//*[@id="root"]/div[4]/div[2]/div[1]/div/div')
                await expect(status).to_be_visible(timeout=200_000)
                status_text = await status.inner_text()
                if "Failed to send transaction" in status_text:
                    logger.error(f'{self.wallet.address} | Failed to swap {token_name}.')
                    return False
                else:
                    logger.success(f'{self.wallet.address} | Successfully swapped {token_name}.')
                    return True
            except Exception as e:
                logger.error(f'{self.wallet.address} | Error occurred: {e}')
                await phoenix_page.reload()
                if attempt < max_retries:
                    logger.info(f'Retrying... (Attempt {attempt + 1}/{max_retries})')
                else:
                    logger.error(f'{self.wallet.address} | Swap failed after {max_retries} attempts.')
                    return False
