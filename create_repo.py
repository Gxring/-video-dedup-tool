import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # 使用Edge浏览器
        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,
            slow_mo=800
        )
        page = await browser.new_page()

        # 打开登录页面
        print("正在打开GitHub登录页面...")
        await page.goto("https://github.com/login")

        # 等待用户登录（检测是否跳转到首页）
        print("请在浏览器中登录，登录后会自动继续...")
        await page.wait_for_url("https://github.com", timeout=300000)
        print("登录成功！")

        # 打开创建仓库页面
        print("正在打开创建仓库页面...")
        await page.goto("https://github.com/new")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # 填写仓库名
        await page.fill("#repository_name", "video-dedup-tool")
        print("已填写仓库名")

        # 填写描述
        await page.fill("#repository_description", "视频去重搬运工具")
        print("已填写描述")

        print("\n请在浏览器中点击 Create repository 按钮创建仓库！")
        print("创建完成后按回车继续...")

        # 等待用户完成操作
        input()

        await browser.close()
        print("浏览器已关闭")

if __name__ == "__main__":
    asyncio.run(main())
