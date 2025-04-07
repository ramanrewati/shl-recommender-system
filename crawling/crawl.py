import os
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode


async def fetch_page(crawler, url, session_id):
    result = await crawler.arun(url=url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS), session_id=session_id)
    if result.success:
        return result.html
    else:
        print(f"Error ")
        return None


async def scrape_main_table(crawler, url):
    html = await fetch_page(crawler, url, "main_table")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
  
    tables = soup.find_all("table")
    if len(tables) < 2:
        table = tables[0]
    else:
        table = tables[1]
    tbody = table.find("tbody")
    if not tbody:
        return []
    rows = tbody.find_all("tr")
    data = []
    for row in rows:
        tds = row.find_all("td")
        if len(tds) >= 3:

            a_tag = tds[0].find("a")
            name = a_tag.get_text(strip=True) if a_tag else ""
            url_link = a_tag["href"] if a_tag and "href" in a_tag.attrs else ""

            if url_link and not url_link.startswith("http"):
                url_link = "https://www.shl.com" + url_link

            remote_testing = "yes" if tds[1].find("span", class_="catalogue__circle -yes") else "no"
            adaptive_irt = "yes" if tds[2].find("span", class_="catalogue__circle -yes") else "no"

            test_tab = tds[3].find_all("span", class_="product-catalogue_key")
            data.append({
                "name": name,
                "url": url_link,
                "remote_testing": remote_testing,
                "adaptive_irt": adaptive_irt,
                "test_tab": test_tab
            })
    return data


async def scrape_detail_page(crawler, url, session_id):
    html = await fetch_page(crawler, url, session_id)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find("div", class_="col-12 col-md-8")
    if not content_div:
        return ""
    detail_text = content_div.get_text(separator="\n", strip=True)

    pdf_links = [a["href"] for a in content_div.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]
    if pdf_links:
        detail_text += "\nPDFs: " + ", ".join(pdf_links)
    return detail_text

async def main():

    base_url = "https://www.shl.com/solutions/products/product-catalog/"

    browser_config = BrowserConfig(
        headless=True
    )
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()
    
    all_table_data = []
    page_start = 0

    while True:
        page_url = f"{base_url}?start={page_start}&type=1&type=1"
        print(f"Scraping main table page: {page_url}")
        table_data = await scrape_main_table(crawler, page_url)

        if not table_data:
            break
        all_table_data.extend(table_data)

        if len(table_data) < 12:
            break
        page_start += 12
    
    print(f"Found {len(all_table_data)} products in the catalog.")


    details = []
    batch_size = 10
    for i in range(0, len(all_table_data), batch_size):
        batch = all_table_data[i:i+batch_size]
        detail_tasks = [
            scrape_detail_page(crawler, row["url"], f"detail_{i + idx}")
            for idx, row in enumerate(batch)
        ]
        print(f"Scraping details for batch {i} to {i + len(batch) - 1}")
        batch_results = await asyncio.gather(*detail_tasks)
        details.extend(batch_results)
    

    for row, detail in zip(all_table_data, details):
        row["detail"] = detail
    

    md_lines = ["# Scraped Product Catalog", ""]
    for row in all_table_data:
        md_lines.append(f"## {row['name']}")
        md_lines.append(f"- **URL:** {row['url']}")
        md_lines.append(f"- **Remote Testing:** {row['remote_testing']}")
        md_lines.append(f"- **Adaptive/IRT:** {row['adaptive_irt']}")
        md_lines.append(f"- **Test Tab:** {row['test_tab']}")
        md_lines.append("")
        md_lines.append("### Detail Content")
        md_lines.append(row.get("detail", "No detail content available"))
        md_lines.append("\n---\n")
    
    output_content = "\n".join(md_lines)
    

    output_filename = "/data/shl-docs.md"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(output_content)
    
    print(f"Scraping complete. Output written to {output_filename}")
    await crawler.close()

if __name__ == "__main__":
    asyncio.run(main())
