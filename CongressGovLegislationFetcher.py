from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm
import requests
from dotenv import load_dotenv
import os
import pandas as pd
import xml.etree.ElementTree as ET
import re

load_dotenv()

class CongressGovLegislationFetcher:
    def __init__(self, api_key, congress, max=10):
        self.api_key = api_key
        self.congress = congress
        self.base_url = "https://api.congress.gov/v3"
        self.data_lock = threading.Lock()
        self.condition = threading.Condition(self.data_lock)
        self.bills = []
        self.is_fetching = False
        self.page = 0
        self.finished = False
        self.limit = 250 if ((max > 250) or max == -1) else max

    @staticmethod
    def calculate_congress_date_range(congress):
        start_year = 1789 + (int(congress) - 1) * 2
        end_year = start_year + 2
        from_date = f"{start_year}-01-03T00:00:00Z"
        to_date = f"{end_year}-01-03T00:00:00Z"
        return from_date, to_date
    
    def get_bill_text(self, congress, bill_number, origin):

        def get_bill_text_url(bill_type, bill_number):
            # Constructing the URL with parameters
            url = f"https://api.congress.gov/v3/bill/{self.congress}/{bill_type}/{bill_number}/text?format=json&api_key={self.api_key}"
            
            # Making the API request
            response = requests.get(url)
            
            # Checking if the request was successful
            if response.status_code == 200:
                data = response.json()
                xml_urls = []
                
                # Looping through text versions to find all XML URLs
                for version in data.get('textVersions', []):
                    for format in version.get('formats', []):
                        if format.get('type') == "Formatted XML":
                            xml_urls.append(format.get('url'))
                
                # Extracting integers from URLs and finding the highest value
                highest_url = None
                highest_value = -1
                for url in xml_urls:
                    # Extracting numbers from the URL
                    numbers = re.findall(r'\d+', url)
                    if numbers:
                        # Assuming the last number in the URL is the relevant one
                        current_value = int(numbers[-1])
                        if current_value > highest_value:
                            highest_value = current_value
                            highest_url = url
                
                return highest_url
            else:
                print(f"Failed to fetch data: HTTP {response.status_code}")
                return None
        origin_code = 's' if origin == 'S' else 'hr' if origin == 'H' else origin
        #url = f"https://www.congress.gov/{self.congress}/bills/{origin_code}{bill_number}/BILLS-{self.congress}{origin_code}{bill_number}i{origin.lower()}.xml"
        url = get_bill_text_url(origin_code, bill_number)
        response = requests.get(url)

        if response.status_code == 200:
            root = ET.fromstring(response.text)

            # Function to recursively extract text from each element
            def extract_text(element, texts=[]):
                if element.text and element.text.strip():
                    texts.append(element.text.strip())
                for child in element:
                    extract_text(child, texts)
                    if child.tail and child.tail.strip():
                        texts.append(child.tail.strip())
                return texts

            # Extract text from the root element
            all_texts = extract_text(root)

            # Join all texts with new lines to preserve text structure
            raw_text = " ".join(all_texts).replace("text/xml", "")
            return raw_text
        else:
            print(f"Error extracting text from {origin_code}{bill_number} at {url}")
            return None

    def fetch_bill_text_concurrently(self, bills_data):
        with ThreadPoolExecutor() as executor:
            future_to_bill = {executor.submit(self.get_bill_text, congress, bill['bill']['number'], bill['bill']['originChamberCode']): bill for bill in bills_data}
            for future in as_completed(future_to_bill):
                bill = future_to_bill[future]
                try:
                    bill_text = future.result()
                    bill['text'] = bill_text  # Append the bill text to the bill data
                except Exception as exc:
                    print(f'{bill["bill"]["number"]} generated an exception: {exc}')
                    bill['text'] = None

    def fetch_bills(self):
        while not self.finished:
            with self.condition:
                if self.is_fetching:
                    return
                self.is_fetching = True

            from_date, to_date = self.calculate_congress_date_range(self.congress)
            offset = self.page * self.limit
            url = f"{self.base_url}/summaries/{self.congress}?fromDateTime={from_date}&toDateTime={to_date}&sort=updateDate+desc&limit={self.limit}&offset={offset}&api_key={self.api_key}"

            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                bills_data = data.get('summaries', [])

                if bills_data:
                    self.fetch_bill_text_concurrently(bills_data)

                with self.condition:
                    self.bills.extend(bills_data)
                    self.page += 1
                    if len(bills_data) < self.limit:
                        self.finished = True

            except requests.exceptions.RequestException as e:
                with self.condition:
                    print(f"Failed to fetch data: {e}")
                    self.finished = True

            finally:
                with self.condition:
                    self.is_fetching = False
                    self.condition.notify_all()

    def next_bill(self):
        with self.condition:
            while not self.bills and not self.finished:
                if not self.is_fetching:
                    threading.Thread(target=self.fetch_bills, daemon=True).start()
                self.condition.wait()

            if self.bills:
                return self.bills.pop(0)
            return None

def run_test(congress, api_key, num_threads=5, num_items=10):
    fetcher = CongressGovLegislationFetcher(api_key=api_key, congress=congress, max=num_items)
    bills = []

    # Shared lock for thread-safe operations on shared data
    lock = threading.Lock()
    # Counter to track the number of fetched bills
    bills_fetched = 0

    def process_bill(progress):
        nonlocal bills_fetched  # Use the nonlocal keyword to modify the outer scope variable
        while True:
            # Only perform the check if num_items is not -1
            if num_items != -1:
                with lock:
                    if bills_fetched >= num_items:
                        break  # Stop if the desired number of bills has been fetched

            bill = fetcher.next_bill()
            if bill:
                should_update_progress = False
                with lock:  # Ensure thread-safe operations
                    # If num_items is -1, continue fetching without checking bills_fetched
                    # Otherwise, check if the limit has not been reached
                    if num_items == -1 or bills_fetched < num_items:
                        bills.append(bill)
                        bills_fetched += 1
                        should_update_progress = True
                    else:
                        break
                if should_update_progress:
                    progress.update(1)
            else:
                # No more bills to fetch
                break

    # Adjust total for tqdm based on num_items
    total_progress = num_items if num_items != -1 else None
    with tqdm(total=total_progress, desc="Fetching bills", unit="bill") as progress:
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(process_bill, progress) for _ in range(num_threads)]
            as_completed(futures)

    print(f"Total bills fetched: {len(bills)}")
    bills_df = pd.DataFrame(bills)
    bills_df.to_csv("data/bills.csv", index=False)
    with open("test.txt", "w", encoding="utf-8") as file:
        file.write(bills_df.iloc[0]['text'])

def get_bill_text_url(congress, bill_type, bill_number, api_key):
    # Constructing the URL with parameters
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/text?format=json&api_key={api_key}"
    
    # Making the API request
    response = requests.get(url)
    
    # Checking if the request was successful
    if response.status_code == 200:
        data = response.json()
        xml_urls = []
        
        # Looping through text versions to find all XML URLs
        for version in data.get('textVersions', []):
            for format in version.get('formats', []):
                if format.get('type') == "Formatted XML":
                    xml_urls.append(format.get('url'))
        
        # Extracting integers from URLs and finding the highest value
        highest_url = None
        highest_value = -1
        for url in xml_urls:
            # Extracting numbers from the URL
            numbers = re.findall(r'\d+', url)
            if numbers:
                # Assuming the last number in the URL is the relevant one
                current_value = int(numbers[-1])
                if current_value > highest_value:
                    highest_value = current_value
                    highest_url = url
        
        return highest_url
    else:
        print(f"Failed to fetch data: HTTP {response.status_code}")
        return None

if __name__ == "__main__":
    api_key = os.getenv('CONGRESSGOV_API_KEY')
    if not api_key:
        raise EnvironmentError("CONGRESSGOV_API_KEY environment variable not set.")
    congress = "117"
    run_test(congress, api_key, num_items=-1)
