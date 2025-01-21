from loguru import logger
from playwright.async_api import BrowserContext, Page, expect
import settings
from data.models import Wallet


class PhoenixTrade:
    def __init__(self, context: BrowserContext, wallet: Wallet):
        self.context = context
        self.wallet = wallet

    async def get_page(self, title_contains: str, url: str = None) -> Page:
        """Возвращает страницу с указанным названием или открывает новую."""
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

    async def get_backpack_page(self) -> Page:
        """Возвращает страницу расширения Backpack."""
        return await self.get_page(
            "Backpack", f'chrome-extension://aflkmfhebedbjioipglgcbcmnbpgliof/options.html?onboarding=true'
        )

    async def get_unlock_page(self) -> Page:
        return await self.get_page("Backpack", 'chrome-extension://aflkmfhebedbjioipglgcbcmnbpgliof/popup.html')

    async def get_phoenix_page(self) -> Page:
        """Возвращает страницу Phoenix."""
        return await self.get_page("Phoenix", settings.phoenix_url)

    async def unlock_wallet_if_needed(self) -> bool:
        """Разблокирует кошелек, если требуется."""
        try:
            backpack_page = await self.get_unlock_page()
            unlock_btn = backpack_page.get_by_text("Unlock")
            if await unlock_btn.is_visible():
                await backpack_page.bring_to_front()
                password_input = backpack_page.get_by_placeholder("Password")
                await password_input.type(settings.extension_password)
                await unlock_btn.click()
                logger.info(f"{self.wallet.address} | Wallet unlocked.")
                return True
            logger.info(f"{self.wallet.address} | Wallet is already unlocked.")
            return True
        except Exception as e:
            logger.warning(f"{self.wallet.address} | Failed to unlock wallet: {e}")
            return False

    async def set_fast_transactions(self):
        """Включает быстрые транзакции, если указано."""
        try:
            phoenix_page = await self.get_phoenix_page()
            settings_btn = phoenix_page.locator('svg.settings-icon')
            await expect(settings_btn.first).to_be_enabled()
            await settings_btn.click()

            fast_tx_btn = phoenix_page.get_by_text('Fast').nth(0)
            await expect(fast_tx_btn.first).to_be_enabled()
            await fast_tx_btn.click()

            close_btn = phoenix_page.locator('ion-icon[icon="close"]').nth(1)
            await expect(close_btn.first).to_be_enabled()
            await close_btn.click()
            logger.info(f"{self.wallet.address} | Fast transactions enabled.")
        except Exception as e:
            logger.warning(f"{self.wallet.address} | Failed to enable fast transactions: {e}")

    async def connect_wallet(self, max_retries: int = 10) -> bool:
        """Подключает кошелек к Phoenix."""
        logger.info(f'{self.wallet.address} | Connecting wallet...')
        for attempt in range(1, max_retries + 1):
            try:
                backpack_page = await self.get_backpack_page()
                phoenix_page = await self.get_phoenix_page()

                connect_wallet_btn = phoenix_page.get_by_role("button", name="Connect Wallet")
                await connect_wallet_btn.click()

                await self.click_if_visible(phoenix_page, 'text="Backpack"', "Backpack Option")
                approve_btn = backpack_page.get_by_text("Approve")
                await approve_btn.click()
                await self.click_if_visible(backpack_page, 'text="Approve"', "Approve Button")
                logger.success(f'{self.wallet.address} | Wallet connected successfully.')
                return True
            except Exception as e:
                logger.error(f'{self.wallet.address} | Connection attempt {attempt} failed: {e}')
                if attempt == max_retries:
                    logger.error(f"{self.wallet.address} | Failed to connect wallet after {max_retries} attempts.")
                    return False

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

    @staticmethod
    async def approve_transaction(page: Page):
        """Подтверждает транзакцию, если требуется."""
        try:
            approve_btn = page.get_by_text("Approve")
            await expect(approve_btn).to_be_visible()
            await approve_btn.click()
            logger.info("Transaction approved.")
        except Exception as e:
            logger.warning(f"Transaction approval failed: {e}")

    async def sell_token(self, token_name: str, amount: float = None, fast: bool = settings.fast,
                         max_retries: int = 10) -> bool:
        """Продает указанный токен. Возвращает True, если продажа выполнена, иначе False."""
        logger.info(f'{self.wallet.address} | Selling {token_name}...')
        phoenix_page = await self.get_phoenix_page()

        for attempt in range(1, max_retries + 1):
            try:
                await phoenix_page.bring_to_front()

                if fast:
                    await self.set_fast_transactions()

                check_amount = phoenix_page.get_by_text("Max:")
                if await check_amount.is_visible():
                    text = await check_amount.text_content()
                    balance = float(text.split("Max: ")[1].strip()) if "Max:" in text else 0
                    logger.info(f'{self.wallet.address} | Balance for {token_name}: {balance}')
                    if balance == 0:
                        logger.warning(f'{self.wallet.address} | Balance is 0 for {token_name}. Skipping wallet.')
                        return False

                    input_amount = min(amount or balance, balance)
                else:
                    logger.warning(f'{self.wallet.address} | Balance locator is not visible for {token_name}. Skipping')
                    return False

                await phoenix_page.locator('input[value=""]').nth(2).type(f'{input_amount}')

                place_order_btn = phoenix_page.locator('button.sc-eqUAAy.sc-fqkvVR.sc-iGgWBj.clpFdu.ecLVOp.dWZrWT')
                btn_text = await place_order_btn.text_content()
                if btn_text in [
                    "Enter an amount", "Insufficient SOL balance", "Insufficient USDC balance",
                    "Insufficient liquidity", "Insufficient size", "Country not supported"
                ]:
                    logger.warning(f'{self.wallet.address} | Place Order Button Not Working: {btn_text}')
                    await phoenix_page.reload()
                    continue

                await place_order_btn.click()
                await self.approve_transaction(phoenix_page)

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
