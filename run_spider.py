from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from lead_generator.spiders.job_spiders import MultiJobSpider
from lead_generator.webhook import send_webhook_if_configured
from pathlib import Path
import os

if __name__ == '__main__':
    settings = get_project_settings()
    results_path = os.getenv("RESULTS_PATH", "results/multi_jobs.tsv")
    Path(results_path).parent.mkdir(parents=True, exist_ok=True)
    settings.set("FEEDS", {
        results_path: {
            "format": "csv",
            "encoding": "utf-8",
            "overwrite": True,
            "delimiter": "\t",
        },
    })
    process = CrawlerProcess(settings)
    process.crawl(MultiJobSpider)
    process.start()
    send_webhook_if_configured(results_path)
