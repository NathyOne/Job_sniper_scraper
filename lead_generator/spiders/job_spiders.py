import scrapy
import re
from datetime import datetime, timedelta
from scrapy_playwright.page import PageMethod


def normalize_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_age_text(posted_text):
    text = (posted_text or "").lower().strip()
    if not text:
        return None
    # parse explicit ISO dates
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return datetime.utcnow() - dt
        except ValueError:
            pass
    if "just posted" in text or "today" in text:
        return timedelta(minutes=0)
    m = re.search(r"(\d+)\s*min", text)
    if m:
        return timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\d+)\s*hour", text)
    if m:
        return timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*day", text)
    if m:
        return timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*week", text)
    if m:
        return timedelta(weeks=int(m.group(1)))
    m = re.search(r"(\d+)\s*month", text)
    if m:
        return timedelta(days=int(m.group(1)) * 30)
    m = re.search(r"posted\s*(\d+)\s*days", text)
    if m:
        return timedelta(days=int(m.group(1)))
    if "hour" in text:
        return timedelta(hours=1)
    return None


def recency_tag(delta):
    if delta is None:
        return "unknown"
    if delta <= timedelta(minutes=30):
        return "minutes"
    if delta <= timedelta(hours=6):
        return "few hours"
    if delta <= timedelta(days=1):
        return "1 day"
    if delta <= timedelta(days=3):
        return "3 days"
    if delta <= timedelta(days=7):
        return "week"
    return "older"


class MultiJobSpider(scrapy.Spider):
    name = "multi_jobs"

    targets = [
        ("Google Jobs", "https://www.google.com/search?q=python+developer+jobs&ibp=htl;jobs"),
        ("LinkedIn", "https://www.linkedin.com/jobs/search?keywords=Python%20Developer&location=United%20States"),
        ("Indeed", "https://www.indeed.com/jobs?q=python+developer&l=United+States"),
        ("Wellfound", "https://wellfound.com/jobs?query=python%20developer"),
        ("Glassdoor", "https://www.glassdoor.com/Job/us-python-developer-jobs-SRCH_IL.0,2_IN1_KO3,19.htm"),
        ("ZipRecruiter", "https://www.ziprecruiter.com/candidate/search?search=python+developer&location=United+States"),
        ("We Work Remotely", "https://weworkremotely.com/remote-jobs/search?term=python"),
        ("Remote OK", "https://remoteok.com/remote-python-jobs"),
        ("Dice", "https://www.dice.com/jobs?q=python+developer&countryCode=US"),
        ("Handshake", "https://joinhandshake.com/jobs?query=python%20developer"),
    ]

    def start_requests(self):
        goto_kwargs = {
            "wait_until": "domcontentloaded",
            "timeout": 60_000,
        }
        playwright_sites = {
            "Google Jobs",
            "LinkedIn",
            "Indeed",
            "Wellfound",
            "Glassdoor",
            "ZipRecruiter",
            "Dice",
            "Handshake",
        }
        for site, url in self.targets:
            meta = {"site": site}
            if site in playwright_sites:
                methods = [PageMethod("wait_for_selector", "body")]
                if site in ("LinkedIn", "Glassdoor", "Handshake", "ZipRecruiter"):
                    methods.append(PageMethod("wait_for_selector", "body"))
                    methods.append(PageMethod("evaluate", "window.scrollBy(0, document.body.scrollHeight);"))
                meta.update(
                    {
                        "playwright": True,
                        "playwright_page_goto_kwargs": goto_kwargs,
                        "playwright_page_methods": methods,
                    }
                )
            yield scrapy.Request(url, callback=self.parse_site, meta=meta)

    def _extract(self, item):
        posted_text = item.get("posted_raw", "")
        delta = parse_age_text(posted_text)
        item["posted_raw"] = normalize_text(posted_text)
        item["recency"] = recency_tag(delta)
        if delta is not None and delta > timedelta(days=7):
            return None
        if item.get("title") and item.get("link"):
            return item
        return None

    def parse_site(self, response):
        site = response.meta.get("site", "unknown")

        if site == "Google Jobs":
            for job in response.css("div[jsname='N9Xkfe'], div[role='article']"):
                data = {
                    "site": site,
                    "title": normalize_text(job.css("div[role='heading']::text").get() or job.css("div span::text").get()),
                    "company": normalize_text(job.css("div[class*='vNEEBe']::text").get()),
                    "location": normalize_text(job.css("div[class*='Qk80Jf']::text").get()),
                    "link": response.urljoin(job.css("a::attr(href)").get(default="")),
                    "posted_raw": normalize_text(job.css("div[aria-label*='ago']::text").get() or job.css("span::text").re_first(r"\d+\s+(?:days|hours|mins?)? ago") or ""),
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "LinkedIn":
            for job in response.css("ul.jobs-search__results-list li"):
                posted_raw = (job.css("time::attr(datetime)").get() or job.css("span::text").re_first(r"\d+\s+\w+ ago") or "")
                data = {
                    "site": site,
                    "title": normalize_text(job.css("h3.base-search-card__title::text").get()),
                    "company": normalize_text(job.css("h4.base-search-card__subtitle a::text").get()),
                    "location": normalize_text(job.css("span.job-search-card__location::text").get()),
                    "link": job.css("a.base-card__full-link::attr(href)").get(),
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "Indeed":
            for job in response.css("div.job_seen_beacon"):
                posted_raw = normalize_text(job.css("span.date::text").get(default=""))
                data = {
                    "site": site,
                    "title": normalize_text(job.css("h2.jobTitle span::text").get()),
                    "company": normalize_text(job.css("span.companyName::text").get()),
                    "location": normalize_text(job.css("div.companyLocation::text").get()),
                    "link": response.urljoin(job.css("a::attr(href)").get(default="")),
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "Wellfound":
            for job in response.css("li.job-result, div.job-result, div.JobCard")[:60]:
                posted_raw = normalize_text(job.css("span.posted::text").get() or job.css("span[data-testid='posted-time']::text").get() or "")
                link = job.css("a::attr(href)").get()
                data = {
                    "site": site,
                    "title": normalize_text(job.css("a.job-link::text").get() or job.css("h3::text").get()),
                    "company": normalize_text(job.css("div.company::text").get() or job.css("p.company::text").get()),
                    "location": normalize_text(job.css("span.location::text").get()),
                    "link": response.urljoin(link) if link else "",
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "Glassdoor":
            for job in response.css("ul.jlGrid li.jl, div.jl")[:60]:
                posted_raw = normalize_text(job.css("span.job-search-key-1::text").get() or job.css("div.d-flex span::text").re_first(r"Posted\s*.*") or "")
                link = job.css("a::attr(href)").get()
                data = {
                    "site": site,
                    "title": normalize_text(job.css("a.jobLink span::text").get() or job.css("a.jobLink::text").get()),
                    "company": normalize_text(job.css("div.jobInfoItem a::text").get() or job.css("div.jobInfoItem::text").get()),
                    "location": normalize_text(job.css("span.subtle::text").get()),
                    "link": response.urljoin(link) if link else "",
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "ZipRecruiter":
            for job in response.css("article.job_result, div.job_result")[:60]:
                posted_raw = normalize_text(job.css("span.posted::text").get() or job.css("div.display--inline-block::text").re_first(r"\d+\s+\w+ ago") or "")
                link = job.css("a::attr(href)").get()
                data = {
                    "site": site,
                    "title": normalize_text(job.css("a.job_link::text").get() or job.css("a::text").get()),
                    "company": normalize_text(job.css("a.job_formatted_employer::text").get() or job.css("div.company span::text").get()),
                    "location": normalize_text(job.css("span.job_result_location::text").get()),
                    "link": response.urljoin(link) if link else "",
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "Dice":
            for job in response.css("div.complete-serp-result-card, div.card")[:60]:
                posted_raw = normalize_text(job.css("div.time::text").get() or job.css("span.listing-date::text").get() or "")
                link = job.css("a::attr(href)").get()
                data = {
                    "site": site,
                    "title": normalize_text(job.css("a.card-title-link::text").get() or job.css("h5::text").get()),
                    "company": normalize_text(job.css("div.company span::text").get()),
                    "location": normalize_text(job.css("div.location span::text").get() or job.css("span.location::text").get()),
                    "link": response.urljoin(link) if link else "",
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "Handshake":
            for job in response.css("div.job-card, li.job-card")[:60]:
                posted_raw = normalize_text(job.css("span.posted-duration::text").get() or job.css("div.posted::text").get() or "")
                link = job.css("a::attr(href)").get()
                data = {
                    "site": site,
                    "title": normalize_text(job.css("h2::text").get() or job.css("a::text").get()),
                    "company": normalize_text(job.css("div.employer::text").get()),
                    "location": normalize_text(job.css("div.location::text").get()),
                    "link": response.urljoin(link) if link else "",
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "We Work Remotely":
            for job in response.css("section.jobs article li.featured, section.jobs article li")[1:]:
                posted_raw = normalize_text(job.css("span.date::text").get() or job.css("time::text").get() or "")
                link = job.css("a::attr(href)").get()
                data = {
                    "site": site,
                    "title": normalize_text(job.css("span.title::text").get()),
                    "company": normalize_text(job.css("span.company::text").get()),
                    "location": normalize_text(job.css("span.region::text").get()),
                    "link": response.urljoin(link) if link else "",
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        if site == "Remote OK":
            for job in response.css("tr.job"):
                posted_raw = normalize_text(job.css("td.time::text").get() or job.css("time::text").get() or "")
                link = job.css("a::attr(href)").get()
                data = {
                    "site": site,
                    "title": normalize_text(job.css("td.company_and_position h2::text").get()),
                    "company": normalize_text(job.css("td.company_and_position h3::text").get()),
                    "location": normalize_text(job.css("div.location::text").get()),
                    "link": response.urljoin(link) if link else "",
                    "posted_raw": posted_raw,
                }
                item = self._extract(data)
                if item:
                    yield item
            return

        # fallback generic extraction with minimal data
        for a in response.css("a")[:60]:
            title = normalize_text(a.xpath("normalize-space(string())").get())
            href = a.attrib.get("href")
            if title and href and len(title) > 5:
                data = {
                    "site": site,
                    "title": title,
                    "company": "",
                    "location": "",
                    "link": response.urljoin(href),
                    "posted_raw": "",
                }
                item = self._extract(data)
                if item:
                    yield item
