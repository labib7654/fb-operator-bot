# -*- coding: utf-8 -*-
"""
محرك كاشف الأرقام اليمنية المستخرج والمدعوم ذاتياً (Yemen Caller ID Engine)
-------------------------------------------------------------------------
1. تنقية وتوحيد كافة صيغ الأرقام اليمنية (+967, 00967, 07..., 7...) بدقة متناهية.
2. كشف شركة الاتصالات (يمن موبايل 4G/CDMA، يو YOU، سبأفون، واي، والهواتف الثابتة بكل المحافظات).
3. فحص سحابي فائق السرعة عبر خيوط معالجة متوازية (Parallel ThreadPool Executor) بمهلة 2 ثانية كحد أقصى.
4. ميزة التخزين المحلي الدائم (Local Caching Vault) لحفظ نتائج البحث فورياً ومنع تكرار الانتظار.
5. لا يظهر أبداً رسالة 'الرقم غير صالح' إذا كان الرقم يمنياً صحيحاً.
"""
from __future__ import annotations

import re
import json
import logging
import concurrent.futures
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

import fb_operator.config as config

logger = logging.getLogger("YemenCallerID")

CACHE_FILE: Path = getattr(config, "DATA_DIR", Path.cwd()) / "yemen_caller_cache.json"


def _load_cache() -> dict[str, Any]:
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(cache_data: dict[str, Any]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class YemenCallerIDAPI:
    """
    محرك كاشف الأرقام اليمنية الشامل (Yemen Phone Directory & Carrier Detector)
    """

    SERVERS = [
        "https://namer1.studioyemenha.site",
        "https://ferggttttwww154w554.cloudfelre.com",
        "https://yttehggsjjkjalllljljsjj3.cloudfelre.com",
        "https://30.studioyemenha.site",
        "https://31.studioyemenha.site"
    ]

    HEADERS = {
        "User-Agent": "Dart/3.0 (dart:io)",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    CARRIERS_MAP = {
        "77": {
            "name": "يمن موبايل (Yemen Mobile)",
            "type": "جوال (CDMA / 4G LTE)",
            "region": "عموم الجمهورية اليمنية",
            "code": "YE-YM"
        },
        "78": {
            "name": "يمن موبايل 4G (Yemen Mobile VoLTE)",
            "type": "جوال فائق السرعة (4G LTE)",
            "region": "عموم الجمهورية اليمنية",
            "code": "YE-YM4G"
        },
        "73": {
            "name": "يو (YOU - MTN سابقاً)",
            "type": "جوال (GSM / 4G)",
            "region": "عموم الجمهورية اليمنية",
            "code": "YE-YOU"
        },
        "71": {
            "name": "سبأفون (Sabafon)",
            "type": "جوال (GSM / 4G)",
            "region": "عموم الجمهورية اليمنية",
            "code": "YE-SBF"
        },
        "70": {
            "name": "واي (Y Telecom)",
            "type": "جوال (GSM / 4G)",
            "region": "عموم الجمهورية اليمنية",
            "code": "YE-Y"
        },
        "01": {
            "name": "الهاتف الثابت - صنعاء وضواحيها",
            "type": "هاتف أرضي / فايبر (PTC)",
            "region": "أمانة العاصمة ومحافظة صنعاء",
            "code": "YE-FIXED-SANAA"
        },
        "02": {
            "name": "الهاتف الثابت - عدن / لحج / أبين",
            "type": "هاتف أرضي / فايبر (PTC)",
            "region": "محافظة عدن والمحافظات المجاورة",
            "code": "YE-FIXED-ADEN"
        },
        "03": {
            "name": "الهاتف الثابت - الحديدة / ريمة",
            "type": "هاتف أرضي (PTC)",
            "region": "محافظة الحديدة والساحل الغربي",
            "code": "YE-FIXED-HOD"
        },
        "04": {
            "name": "الهاتف الثابت - تعز / إب",
            "type": "هاتف أرضي (PTC)",
            "region": "محافظتي تعز وإب",
            "code": "YE-FIXED-TAIZ"
        },
        "05": {
            "name": "الهاتف الثابت - حضرموت / شبوة / المهرة",
            "type": "هاتف أرضي (PTC)",
            "region": "حضرموت والمحافظات الشرقية",
            "code": "YE-FIXED-HADRAMOUT"
        },
        "06": {
            "name": "الهاتف الثابت - مأرب / الجوف / البيضاء",
            "type": "هاتف أرضي (PTC)",
            "region": "مأرب والبيضاء والجوف",
            "code": "YE-FIXED-MARIB"
        },
        "07": {
            "name": "الهاتف الثابت - ذمار / الضالع / حجة",
            "type": "هاتف أرضي (PTC)",
            "region": "ذمار والضالع وحجة والمحويت",
            "code": "YE-FIXED-DHAMAR"
        }
    }

    @classmethod
    def sanitize_number(cls, raw_phone: str) -> str:
        """
        تنظيف رقم الهاتف وتوحيد صيغته بدقة متناهية:
        يحول +967771234567 أو 00967771234567 أو 0771234567 إلى 771234567
        """
        if not raw_phone:
            return ""
        digits = re.sub(r"\D", "", str(raw_phone).strip())
        if digits.startswith("00967"):
            digits = digits[5:]
        elif digits.startswith("967"):
            digits = digits[3:]

        # إذا بدأ بصفر وكان جوالاً (9 أرقام بعد الصفر مثل 0771234567) نحذف الصفر الأولي
        if digits.startswith("0") and len(digits) == 10 and digits[1] == "7":
            digits = digits[1:]

        return digits

    @classmethod
    def detect_carrier_info(cls, phone: str) -> dict[str, str]:
        """استخراج تفاصيل شبكة الاتصال والمحافظة للرقم"""
        if not phone or len(phone) < 2:
            return {
                "name": "شبكة غير معروفة",
                "type": "غير محدد",
                "region": "اليمن",
                "code": "UNKNOWN"
            }
        prefix = phone[:2]
        if prefix in cls.CARRIERS_MAP:
            return cls.CARRIERS_MAP[prefix]

        if phone.startswith("0") and len(phone) >= 2:
            sub = phone[:2]
            if sub in cls.CARRIERS_MAP:
                return cls.CARRIERS_MAP[sub]

        return {
            "name": "شبكة اتصالات يمنية",
            "type": "اتصالات محلية",
            "region": "الجمهورية اليمنية",
            "code": "YE-OTHER"
        }

    @classmethod
    def validate_yemen_number(cls, clean_phone: str) -> tuple[bool, str]:
        """
        التحقق الصارم من صحة الرقم اليمني:
        - الجوال: 9 أرقام تبدأ بـ 70, 71, 73, 77, 78
        - الثابت: 7 أو 8 أرقام تبدأ بـ 01 إلى 07
        """
        if not clean_phone:
            return False, "لم يتم إدخال أي رقم للبحث."

        if len(clean_phone) == 9 and clean_phone[:2] in ("77", "78", "73", "71", "70"):
            return True, "رقم جوال يمني صالح"

        if clean_phone.startswith("0") and len(clean_phone) in (7, 8) and clean_phone[:2] in cls.CARRIERS_MAP:
            return True, "رقم هاتف ثابت صالح"

        if clean_phone.startswith(("1", "2", "3", "4", "5", "6", "7")) and len(clean_phone) in (6, 7):
            return True, "رقم هاتف أرضي محلي"

        return False, "صيغة الرقم غير معتمدة. أرقام الجوال اليمنية تتكون من 9 أرقام وتبدأ بـ (77, 78, 73, 71, 70)."

    @classmethod
    def _query_single_server(cls, base: str, phone: str) -> list[str]:
        """استعلام سيرفر محدد بمهلة سريعة جداً لمنع تعليق خيوط المعالجة"""
        url = f"{base}/api/arkamalyemenphone/2025/getname/{phone}"
        # 1. تجربة GET
        try:
            req = urllib.request.Request(url, headers=cls.HEADERS)
            with urllib.request.urlopen(req, timeout=0.7) as resp:
                if resp.status == 200:
                    content = resp.read().decode("utf-8", errors="ignore")
                    extracted = cls._extract_names_from_json(json.loads(content))
                    if extracted:
                        return extracted
        except Exception:
            pass

        # 2. تجربة POST مع int64
        try:
            if phone.isdigit():
                payload = json.dumps({"phone": int(phone)}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers=cls.HEADERS, method="POST")
                with urllib.request.urlopen(req, timeout=0.7) as resp:
                    if resp.status == 200:
                        content = resp.read().decode("utf-8", errors="ignore")
                        extracted = cls._extract_names_from_json(json.loads(content))
                        if extracted:
                            return extracted
        except Exception:
            pass

        return []

    @classmethod
    def lookup_number(cls, raw_phone: str) -> dict[str, Any]:
        """
        البحث الشامل عن اسم صاحب الرقم عبر الخوادم السحابية المتوازية والخزنة المحلية
        """
        phone = cls.sanitize_number(raw_phone)
        is_valid, validation_msg = cls.validate_yemen_number(phone)
        carrier_info = cls.detect_carrier_info(phone)

        if not is_valid:
            return {
                "success": False,
                "is_valid": False,
                "phone": phone or raw_phone,
                "carrier": carrier_info["name"],
                "carrier_type": carrier_info["type"],
                "region": carrier_info["region"],
                "error": validation_msg,
                "names": []
            }

        # 1. الاستعلام عبر حوض الجلسات المتعددة المتناوبة مع الكاش الفوري (Multi-Session Rotating Pool)
        try:
            from fb_operator.multi_session_pool import MultiSessionPoolManager
            pool_mgr = MultiSessionPoolManager.get_instance()
            cached_entry = pool_mgr.get_cached(phone)
            if cached_entry and cached_entry.get("names"):
                return {
                    "success": True,
                    "is_valid": True,
                    "phone": phone,
                    "carrier": carrier_info["name"],
                    "carrier_type": carrier_info["type"],
                    "region": carrier_info["region"],
                    "primary_name": cached_entry.get("primary_name") or (cached_entry.get("names") or [""])[0],
                    "records_count": cached_entry.get("records_count") or len(cached_entry.get("names", [])),
                    "names": cached_entry["names"],
                    "source": "قاعدة البيانات المحلية (سريع ⚡)"
                }

            active_sessions = pool_mgr.discover_sessions()
            if active_sessions:
                b_res = pool_mgr.query_number_sync(phone, timeout=12.0)
                if b_res.get("success"):
                    names = b_res.get("names", [])
                    p_name = b_res.get("primary_name")
                    rec_count = b_res.get("records_count", len(names))
                    if names and names[0] not in ("غير مسجل", "لم يتم العثور على اسم مسجل لهذا الرقم في قاعدة البيانات."):
                        return {
                            "success": True,
                            "is_valid": True,
                            "phone": phone,
                            "carrier": carrier_info["name"],
                            "carrier_type": carrier_info["type"],
                            "region": carrier_info["region"],
                            "primary_name": p_name or names[0],
                            "records_count": rec_count,
                            "names": names,
                            "source": b_res.get("source") or "كاشف الأرقام 🌐"
                        }
                    else:
                        return {
                            "success": True,
                            "is_valid": True,
                            "phone": phone,
                            "carrier": carrier_info["name"],
                            "carrier_type": carrier_info["type"],
                            "region": carrier_info["region"],
                            "primary_name": "غير مسجل",
                            "records_count": 0,
                            "names": [],
                            "note": f"الرقم صالح ويتبع شبكة {carrier_info['name']}. لا يوجد اسم معلن له حالياً في السجلات."
                        }
        except Exception as _pool_err:
            logger.debug(f"Multi-session pool query fallback: {_pool_err}")

        cache = _load_cache()
        if phone in cache and cache[phone].get("names"):
            cached_entry = cache[phone]
            return {
                "success": True,
                "is_valid": True,
                "phone": phone,
                "carrier": carrier_info["name"],
                "carrier_type": carrier_info["type"],
                "region": carrier_info["region"],
                "names": cached_entry.get("names", []),
                "source": "السجل المحفوظ (سريع ⚡)"
            }

        # 2. استعلام متوازٍ وسريع بمهلة إجمالية 2.2 ثانية
        found_names: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(cls.SERVERS)) as executor:
            future_to_srv = {
                executor.submit(cls._query_single_server, srv, phone): srv
                for srv in cls.SERVERS
            }
            try:
                for future in concurrent.futures.as_completed(future_to_srv, timeout=2.2):
                    res_names = future.result()
                    if res_names:
                        found_names = res_names
                        break
            except Exception:
                pass

        if found_names:
            cache[phone] = {
                "phone": phone,
                "carrier": carrier_info["name"],
                "names": found_names
            }
            _save_cache(cache)

            return {
                "success": True,
                "is_valid": True,
                "phone": phone,
                "carrier": carrier_info["name"],
                "carrier_type": carrier_info["type"],
                "region": carrier_info["region"],
                "names": found_names,
                "source": "الدليل السحابي المباشر 🌐"
            }

        # الرقم صالح 100% ولكن قاعدة الأسماء السحابية تحت المزامنة أو لا يوجد اسم مسجل
        return {
            "success": True,
            "is_valid": True,
            "phone": phone,
            "carrier": carrier_info["name"],
            "carrier_type": carrier_info["type"],
            "region": carrier_info["region"],
            "names": [],
            "note": f"الرقم صالح ويتبع شبكة {carrier_info['name']} ({carrier_info['region']}). لا يوجد اسم معلن له حالياً في السجلات السحابية."
        }

    @staticmethod
    def _extract_names_from_json(data: Any) -> list[str]:
        names: list[str] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    n = item.get("name") or item.get("Name") or item.get("username")
                    if n and isinstance(n, str) and n.strip() and n.strip() not in names:
                        names.append(n.strip())
                elif isinstance(item, str) and item.strip() and item.strip() not in names:
                    names.append(item.strip())
        elif isinstance(data, dict):
            raw = data.get("names") or data.get("data") or data.get("name") or data.get("Name")
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.strip() and item.strip() not in names:
                        names.append(item.strip())
                    elif isinstance(item, dict):
                        n = item.get("name") or item.get("Name")
                        if n and isinstance(n, str) and n.strip() not in names:
                            names.append(n.strip())
            elif isinstance(raw, str) and raw.strip():
                names.append(raw.strip())
        return names
