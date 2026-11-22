"""内置城市表：坐标 + IANA 时区。

只放「自己会用到」的几个城市；Open-Meteo 的 geocoding 对中文城市名召回不稳，
所以不做在线搜索，查不到就 400，让调用方明确失败。

字段顺序是 (纬度, 经度)，中国城市经度 100–125 全部超出纬度上限，
写反了会在 import 时直接抛 ValueError，不会拖到上游 400 才发现。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float
    timezone: str

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError(f"{self.name} 的纬度越界：{self.latitude}（应在 -90~90）")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError(f"{self.name} 的经度越界：{self.longitude}（应在 -180~180）")


DEFAULT_CITY = "杭州"

CITIES: dict[str, City] = {
    "杭州": City("杭州", 30.274, 120.155, "Asia/Shanghai"),
    "上海": City("上海", 31.230, 121.473, "Asia/Shanghai"),
    "北京": City("北京", 39.904, 116.407, "Asia/Shanghai"),
    "广州": City("广州", 23.129, 113.264, "Asia/Shanghai"),
    "深圳": City("深圳", 22.543, 114.057, "Asia/Shanghai"),
    "成都": City("成都", 30.572, 104.066, "Asia/Shanghai"),
    "南京": City("南京", 32.060, 118.796, "Asia/Shanghai"),
    "武汉": City("武汉", 30.593, 114.305, "Asia/Shanghai"),
}


def find_city(name: str | None) -> City | None:
    """不传就用默认城市；传了就必须命中。"""
    if not name:
        return CITIES[DEFAULT_CITY]
    return CITIES.get(name.strip())


def city_names() -> list[str]:
    return list(CITIES)
