"""One read-only attempt per fixed article; never print response or exception bodies."""
import json

import meta_ads_tracker_collect as transport
from meta_ads_tracker_contract import ContractError


class RedirectProbe(transport._RestrictedRedirectHandler):
    observed_status = None

    def redirect_request(self, request, fp, code, message, headers, newurl):
        type(self).observed_status = code
        return super().redirect_request(request, fp, code, message, headers, newurl)


def main():
    with open("config/meta_ads_personal_feed_sources.json", encoding="utf-8") as file:
        config = json.load(file)
    source = next(s for s in config["sources"] if s["id"] == "social-media-today-meta-ads")
    urls = {
        "ai_ranking": "https://www.socialmediatoday.com/news/meta-says-its-expanded-processing-capacity-is-driving-ad-results/873133/",
        "campaign_data": "https://www.socialmediatoday.com/news/meta-says-advertisers-should-let-campaigns-gather-data/833906/",
    }
    transport.MAX_FETCH_ATTEMPTS = 1
    transport._RestrictedRedirectHandler = RedirectProbe
    original_build_opener = transport.urllib.request.build_opener
    status = {"value": None}

    class CapturingOpener:
        def __init__(self, opener):
            self.opener = opener

        def open(self, *args, **kwargs):
            response = self.opener.open(*args, **kwargs)
            status["value"] = response.status
            return response

    def build_opener(*handlers):
        return CapturingOpener(original_build_opener(*handlers))

    transport.urllib.request.build_opener = build_opener
    for case, url in urls.items():
        RedirectProbe.observed_status = None
        status["value"] = None
        request = {**source, "fetchUrl": url, "parser": "article_page_html", "expectedContentTypes": ["text/html"],
                   "transport": {**source["transport"], "maxResponseBytes": 1_048_576, "maxRedirects": 0}}
        failure = None
        try:
            transport._request(request, 5)
        except transport.SourceFetchError as error:
            failure = "http_error" if error.reason.startswith("http_status=") else "network_error"
            if failure == "http_error":
                status["value"] = int(error.reason.split("=", 1)[1])
        except ContractError as error:
            message = str(error)
            failure = ("redirect_rejected" if RedirectProbe.observed_status else
                       "content_type" if "Content-Type" in message else
                       "response_size" if "byte limit" in message else
                       "dns_validation" if "hostname" in message else "contract_error")
        except TimeoutError:
            failure = "timeout"
        except OSError:
            failure = "network_error"
        print(json.dumps({"case": case, "http_status": status["value"] or RedirectProbe.observed_status,
                          "redirect_observed": RedirectProbe.observed_status is not None,
                          "failure_kind": failure, "attempts": 1}))


if __name__ == "__main__":
    main()
