import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # 登录GitHub
        print("正在打开GitHub登录页面...")
        await page.goto("https://github.com/login")
        await page.wait_for_load_state("networkidle")

        # 输入用户名
        await page.fill("#login_field", "Guoxurui1")
        # 输入密码
        await page.fill("#password", "")
        print("请输入密码，然后按回车登录...")

        # 等待用户手动输入密码并登录
        await page.wait_for_url("**/github.com", timeout=120000)
        print("登录成功！")

        # 创建新仓库
        print("正在创建新仓库...")
        await page.goto("https://github.com/new")
        await page.wait_for_load_state("networkidle")

        # 填写仓库名
        await page.fill("#repository_name", "video-dedup-tool")

        # 填写描述
        await page.fill("#repository_description", "视频去重搬运工具")

        # 点击创建按钮
        await page.click("button:has-text('Create repository')")
        await page.wait_for_load_state("networkidle")

        print("仓库创建成功！")
        print("仓库地址: https://github.com/Guoxurui1/video-dedup-tool")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
