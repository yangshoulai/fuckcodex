"""Pydoll 浏览器自动化通用辅助工具。"""

import asyncio
import time

from pydoll.browser.tab import Tab
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import ElementNotFound


async def wait_url(tab: Tab, url_flags: list[str], raise_exc: bool = True, timeout_sec: int = 10, interval_sec: int = 0.5) -> str | None:
    """等待页面 URL 包含目标标识。

    参数:
        tab: 当前浏览器标签页。
        url_flags: URL 命中标识列表，命中任意一个即返回。
        raise_exc: 超时时是否抛出异常。
        timeout_sec: 最大等待秒数。
        interval_sec: 轮询间隔秒数。

    返回:
        命中时返回当前 URL；超时且不抛异常时返回 None。

    异常:
        ElementNotFound: 超时且 raise_exc=True 时抛出。
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        current_url = (await tab.current_url or "").strip()
        for flag in url_flags:
            if flag in current_url:
                return current_url
        await asyncio.sleep(interval_sec)
    if raise_exc:
        raise ElementNotFound(f"等待网页 {url_flags} 超时")
    return None


async def wait_url_or_element(
        tab: Tab,
        url_flags: list[str],
        ele_selectors: list[str],
        raise_exc: bool = True,
        timeout_sec: int = 10,
        interval_sec: int = 0.5) -> tuple[str | None, WebElement | None]:
    """等待“URL 命中”或“元素出现”两种条件之一。

    参数:
        tab: 当前浏览器标签页。
        url_flags: URL 命中标识列表，命中任意一个即返回 (url, None)。
        ele_selectors: 元素选择器列表，命中任意一个即返回 (None, element)。
        raise_exc: 超时时是否抛出异常。
        timeout_sec: 最大等待秒数。
        interval_sec: 轮询间隔秒数。

    返回:
        二元组 (url, element)：
        - URL 命中时: (命中 URL, None)
        - 元素命中时: (None, 命中元素)
        - 超时且不抛异常时: (None, None)

    异常:
        ElementNotFound: 超时且 raise_exc=True 时抛出。
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        current_url = (await tab.current_url or "").strip()
        for flag in url_flags:
            if flag in current_url:
                return current_url, None
        for ele_selector in ele_selectors:
            element = await tab.query(ele_selector, raise_exc=False, timeout=0)
            if element:
                return None, element
        await asyncio.sleep(interval_sec)
    if raise_exc:
        raise ElementNotFound(f"等待网页 {url_flags} 或 元素 {ele_selectors} 超时")
    return None, None


async def get_live_value(input_el: WebElement | str, tab: Tab | None = None) -> str:
    """读取输入框实时 value（非属性初始值）。

    参数:
        input_el: WebElement 或元素选择器字符串。
        tab: 当 input_el 为选择器字符串时必须提供，用于查询元素。

    返回:
        输入框当前 value 字符串。

    异常:
        ValueError: input_el 为选择器字符串但未提供 tab。
        ElementNotFound: 根据选择器未找到元素。
    """
    if isinstance(input_el, str):
        if tab is None:
            raise ValueError("请指定 tab")
        input_el = await tab.query(input_el, raise_exc=False)
        if input_el is None:
            raise ElementNotFound(f"未找到元素 {input_el}")
    resp = await input_el.execute_script(
        "return (this.value ?? '').toString()",
        return_by_value=True,
    )
    return str(resp.get("result", {}).get("result", {}).get("value", "") or "")


async def ensure_input(tab: Tab, ele_selector: str, value: str, timeout_sec: int = 10, try_times: int = 3) -> bool:
    """强制写入输入框并校验回填结果，避免输入丢失。

    逻辑:
        每次尝试都会执行 focus -> clear -> type_text -> 读取实时 value 校验。
        任意一次校验成功即返回 True；全部失败返回 False。

    参数:
        tab: 当前浏览器标签页。
        ele_selector: 输入框选择器。
        value: 目标写入值。
        timeout_sec: 单次查询元素的超时秒数。
        try_times: 最大重试次数。

    返回:
        是否写入成功。
    """
    target_value = str(value)
    for index in range(try_times):
        # 每轮重查元素，降低 DOM 刷新导致的句柄失效风险。
        input_el = await tab.query(ele_selector, timeout_sec)
        await input_el.focus()
        await input_el.clear()
        await input_el.type_text(target_value, humanize=True)
        current_value = await get_live_value(input_el)
        if current_value == target_value:
            return True
    return False


async def get_cookies(tab: Tab) -> dict[str, str]:
    """获取当前标签页所有 Cookie。

    参数:
        tab: 当前浏览器标签页。

    返回:
        Cookie 列表。
    """
    cookies = await tab.get_cookies()
    return {c['name']: c['value'] for c in cookies}


async def get_cookie(tab: Tab, name: str) -> str | None:
    """获取当前标签页指定 Cookie 值。

    参数:
        tab: 当前浏览器标签页。
        name: Cookie 名称。

    返回:
        Cookie 值。
    """
    cookies = await get_cookies(tab)
    return cookies.get(name, None)
