import json, unittest
from pathlib import Path
from meta_ads_tracker_official_canary import observe, validate_config

CONFIG=validate_config(json.loads((Path(__file__).parents[1]/"config/meta_ads_official_canaries.json").read_text()))
class CanaryTest(unittest.TestCase):
 def test_429_is_observed_not_failed(self):
  report=observe(CONFIG,1,lambda url,method,timeout:(429,url,{"Content-Type":"text/html","Retry-After":"60"}))
  self.assertEqual(report["summary"]["rate_limited"],3); self.assertFalse(report["responseBodyStored"]); self.assertTrue(report["artifactOnly"])
 def test_reachable_and_unexpected_are_classified(self):
  report=observe(CONFIG,1,lambda url,method,timeout:(200,url,{"Content-Type":"text/html; charset=utf-8"}) if "graph" in url else (403,url,{"Content-Type":"text/html"}))
  self.assertEqual(report["summary"]["reachable"],1); self.assertEqual(report["summary"]["unexpected_response"],2)
