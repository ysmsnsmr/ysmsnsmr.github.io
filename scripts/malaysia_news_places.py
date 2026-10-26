"""Approximate reference locations for place names used in Malaysia News."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    key: str
    label: str
    latitude: float
    longitude: float
    zoom: int
    aliases: tuple[str, ...]


# Coordinates indicate the area, not the precise location of a reported event.
PLACES = (
    Place("johor", "ジョホール州", 2.0, 103.5, 8, ("ジョホール州", "Johor")),
    Place("kedah", "ケダ州", 6.1, 100.5, 8, ("ケダ州", "Kedah")),
    Place("kelantan", "ケランタン州", 5.4, 102.0, 8, ("ケランタン州", "Kelantan")),
    Place("melaka", "マラッカ州", 2.3, 102.3, 9, ("マラッカ州", "Melaka")),
    Place("negeri-sembilan", "ヌグリ・スンビラン州", 2.8, 102.2, 9, ("ヌグリ・スンビラン州", "Negeri Sembilan")),
    Place("pahang", "パハン州", 3.8, 103.2, 8, ("パハン州", "Pahang")),
    Place("penang", "ペナン州", 5.4, 100.3, 9, ("ペナン州", "Penang", "Pulau Pinang")),
    Place("perak", "ペラ州", 4.8, 101.1, 8, ("ペラ州", "Perak")),
    Place("perlis", "ペルリス州", 6.5, 100.2, 9, ("ペルリス州", "Perlis")),
    Place("sabah", "サバ州", 5.6, 116.5, 7, ("サバ州", "Sabah")),
    Place("sarawak", "サラワク州", 3.1, 113.0, 7, ("サラワク州", "Sarawak")),
    Place("selangor", "セランゴール州", 3.1, 101.5, 9, ("セランゴール州", "Selangor")),
    Place("terengganu", "トレンガヌ州", 5.0, 103.0, 8, ("トレンガヌ州", "Terengganu")),
    Place("kuala-lumpur", "クアラルンプール", 3.14, 101.69, 11, ("クアラルンプール", "Kuala Lumpur")),
    Place("putrajaya", "プトラジャヤ", 2.93, 101.68, 11, ("プトラジャヤ", "Putrajaya")),
    Place("labuan", "ラブアン", 5.28, 115.24, 11, ("ラブアン", "Labuan")),
    Place("klang-valley", "クランバレー", 3.1, 101.55, 9, ("クランバレー", "Klang Valley")),
    Place("tawau", "タワウ", 4.25, 117.89, 11, ("タワウ", "Tawau")),
    Place("kuching", "クチン", 1.55, 110.35, 11, ("クチン", "Kuching")),
    Place("serian", "セリアン", 1.17, 110.57, 11, ("セリアン", "Serian")),
    Place("tebedu", "テブドゥ", 1.02, 110.36, 11, ("テブドゥ", "Tebedu")),
    Place("pasir-gudang", "パシル・グダン", 1.46, 103.9, 11, ("パシル・グダン", "Pasir Gudang")),
    Place("tanjung-tokong", "タンジュン・トコン", 5.46, 100.3, 12, ("タンジュン・トコン", "Tanjung Tokong")),
    Place("tanjung-bungah", "タンジュン・ブンガ", 5.47, 100.29, 12, ("タンジュン・ブンガ", "Tanjung Bungah")),
    Place("gua-musang", "グア・ムサン", 4.88, 101.96, 11, ("グア・ムサン", "Gua Musang")),
    Place("raub", "ラウブ", 3.8, 101.85, 11, ("ラウブ", "Raub")),
    Place("george-town", "ジョージタウン", 5.41, 100.34, 11, ("ジョージタウン", "George Town")),
    Place("ipoh", "イポー", 4.6, 101.09, 11, ("イポー", "Ipoh")),
    Place("johor-bahru", "ジョホールバル", 1.49, 103.76, 11, ("ジョホールバル", "Johor Bahru")),
    Place("shah-alam", "シャー・アラム", 3.07, 101.52, 11, ("シャー・アラム", "Shah Alam")),
    Place("petaling-jaya", "プタリン・ジャヤ", 3.11, 101.64, 11, ("プタリン・ジャヤ", "Petaling Jaya")),
    Place("kota-kinabalu", "コタキナバル", 5.98, 116.07, 11, ("コタキナバル", "Kota Kinabalu")),
    Place("kota-bharu", "コタバル", 6.13, 102.24, 11, ("コタバル", "Kota Bharu")),
)

BY_KEY = {place.key: place for place in PLACES}
ALIASES = tuple(sorted(
    ((alias, place) for place in PLACES for alias in place.aliases),
    key=lambda entry: len(entry[0]),
    reverse=True,
))


def find_places(text: str) -> list[Place]:
    """Find explicit names only; never infer an event location from its source."""
    matches: list[tuple[int, Place]] = []
    occupied: list[tuple[int, int]] = []
    for alias, place in ALIASES:
        start = 0
        while (position := text.find(alias, start)) >= 0:
            end = position + len(alias)
            if not any(position < other_end and end > other_start for other_start, other_end in occupied):
                occupied.append((position, end))
                matches.append((position, place))
            start = end
    found: list[Place] = []
    for _, place in sorted(matches, key=lambda match: match[0]):
        if place not in found:
            found.append(place)
    return found
