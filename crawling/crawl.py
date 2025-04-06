import os
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Helper: fetch a page’s HTML using crawl4ai
async def fetch_page(crawler, url, session_id):
    result = await crawler.arun(url=url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS), session_id=session_id)
    if result.success:
        return result.html
    else:
        print(f"Error fetching {url}")
        return None

# Scrape the main table (the second table on the page)
async def scrape_main_table(crawler, url):
    html = await fetch_page(crawler, url, "main_table")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    # Locate all tables – we assume the second one is the target
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
            # First column: extract name and URL from the <a> tag.
            a_tag = tds[0].find("a")
            name = a_tag.get_text(strip=True) if a_tag else ""
            url_link = a_tag["href"] if a_tag and "href" in a_tag.attrs else ""
            # Ensure URL is absolute
            if url_link and not url_link.startswith("http"):
                url_link = "https://www.shl.com" + url_link
            # Second and third columns: check for <span> with class "catalogue__circle -yes"
            remote_testing = "yes" if tds[1].find("span", class_="catalogue__circle -yes") else "no"
            adaptive_irt = "yes" if tds[2].find("span", class_="catalogue__circle -yes") else "no"
            # Add the test tab type as provided (here it's always "1" since we ignore type=2)
            test_tab = tds[3].find_all("span", class_="product-catalogue_key")
            data.append({
                "name": name,
                "url": url_link,
                "remote_testing": remote_testing,
                "adaptive_irt": adaptive_irt,
                "test_tab": test_tab
            })
    return data

# Scrape the detail page for each product.
# We extract the text content under the div with class "col-12 col-md-8"
# and collect any PDF links found in that section.
async def scrape_detail_page(crawler, url, session_id):
    html = await fetch_page(crawler, url, session_id)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find("div", class_="col-12 col-md-8")
    if not content_div:
        return ""
    detail_text = content_div.get_text(separator="\n", strip=True)
    # Find PDF links in this div
    pdf_links = [a["href"] for a in content_div.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]
    if pdf_links:
        detail_text += "\nPDFs: " + ", ".join(pdf_links)
    return detail_text

async def main():
    # Base URL for the product catalog
    base_url = "https://www.shl.com/solutions/products/product-catalog/"
    # Set up crawl4ai with a minimal browser config for fast, headless operation.
    browser_config = BrowserConfig(
        headless=True,
        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
    )
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()
    
    all_table_data = []
    page_start = 0
    # Loop over paginated pages.
    while True:
        page_url = f"{base_url}?start={page_start}&type=1&type=1"
        print(f"Scraping main table page: {page_url}")
        table_data = await scrape_main_table(crawler, page_url)
        # If no rows are returned, assume no more pages.
        if not table_data:
            break
        all_table_data.extend(table_data)
        # Assuming each page shows 12 entries; stop if fewer than 12 rows found.
        if len(table_data) < 12:
            break
        page_start += 12
    
    print(f"Found {len(all_table_data)} products in the catalog.")

    # Process detail page scraping in batches of 10.
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
    
    # Append detail content to each product’s data.
    for row, detail in zip(all_table_data, details):
        row["detail"] = detail
    
    # Format output in Markdown.
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
    
    # Write the output to a markdown file.
    output_filename = "scraped.md"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(output_content)
    
    print(f"Scraping complete. Output written to {output_filename}")
    await crawler.close()

if __name__ == "__main__":
    asyncio.run(main())
