#!/usr/bin/env python3
# Based on https://github.com/greaselovely/maxmind-ipv6-edl

import argparse
import csv
import logging
import netaddr
import os
import requests
import shutil
import sys
import zipfile
from pathlib import Path

# Downloader


class Downloader(object):
    def __init__(self, url, output_file):
        self.url = url
        self.output_file = output_file

    def is_downloaded(self):
        return self.output_file.exists()

    def download(self):
        logging.debug(f"Downloading {self.output_file}...")
        response = requests.get(self.url)
        if response.status_code == 200:
            with open(self.output_file, "wb") as f:
                f.write(response.content)
            logging.debug(f"Downloaded and saved to {self.output_file}")
        else:
            logging.error(f"Failed to download. Status code: {response.status_code}")
            sys.exit(1)


# GeoLite2DatabaseBase


class GeoLite2DatabaseBase(object):
    def __init__(self, url, zip_file, extract_dir):
        self.downloader = Downloader(url, zip_file)
        self.zip_file = zip_file
        self.extract_dir = extract_dir

    def is_downloaded(self):
        return self.downloader.is_downloaded()

    def download(self):
        self.downloader.download()
        return self

    def extract(self):
        logging.debug(f"Extracting {self.zip_file}...")
        with zipfile.ZipFile(self.zip_file, "r") as zip_ref:
            zip_ref.extractall(self.extract_dir)
        logging.debug(f"Database extracted to {self.extract_dir}")
        return self

    def find(self, file_name):
        """
        Searches for a specified file within the extracted folder.
        Returns the full path to the file if found.
        Raises FileNotFoundError if the file is not found.
        """
        for root, _, files in os.walk(self.extract_dir):
            for file in files:
                if file == file_name:
                    found_path = os.path.join(root, file)
                    logging.debug(f"Found {file_name} at {found_path}")
                    return found_path
        raise FileNotFoundError(f"{file_name} not found in extracted data")


# GeoLite2DatabaseCountry


class GeoLite2DatabaseCountry(GeoLite2DatabaseBase):
    def __init__(self, url, extract_dir):
        zip_file_name = extract_dir / "GeoLite2-Country.zip"
        zip_extract_dir = extract_dir / "geolite2_data"
        super().__init__(url, zip_file_name, zip_extract_dir)
        self.country_mapping = {}
        self.ipv4_blocks = {}
        self.ipv6_blocks = {}

    def extract_geoname_country_mapping(self):
        """
        Creates a mapping of GeoName IDs to country ISO codes using the locations CSV file.
        Returns a dictionary with GeoName IDs as keys and country ISO codes as values.
        """
        mapping = {}
        locations_csv = self.find("GeoLite2-Country-Locations-en.csv")
        with open(locations_csv, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                geoname_id = row["geoname_id"]
                country_code = row["country_iso_code"]
                mapping[geoname_id] = country_code
        logging.debug(f"Loaded {len(mapping)} geoname_id to country code mappings")
        self.country_mapping = mapping
        return self

    def extract_ipv4_blocks(self, country_codes):
        self.ipv4_blocks = self.__extract_blocks(
            "GeoLite2-Country-Blocks-IPv4.csv", country_codes
        )
        return self

    def extract_ipv6_blocks(self, country_codes):
        self.ipv6_blocks = self.__extract_blocks(
            "GeoLite2-Country-Blocks-IPv6.csv", country_codes
        )
        return self

    def __extract_blocks(self, filename, country_codes):
        """
        Extracts IP networks for the specified blocked countries from the GeoLite2 CSV file.
        Returns a dictionary with country codes as keys and lists of IP networks as values.
        """
        blocks = {}
        csv_path = self.find(filename)

        with open(csv_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                geoname_id = row.get("registered_country_geoname_id", "")
                if geoname_id in self.country_mapping:
                    country_code = self.country_mapping[geoname_id]
                    if country_code in country_codes:
                        if country_code not in blocks:
                            blocks[country_code] = []
                        blocks[country_code].append(netaddr.IPNetwork(row["network"]))
        for country_code in country_codes:
            logging.debug(f"Found {len(blocks[country_code])} block(s)")
        return blocks


# GeoLite2DatabaseASN


class GeoLite2DatabaseASN(GeoLite2DatabaseBase):
    def __init__(self, url, extract_dir):
        zip_file_name = extract_dir / "GeoLite2-ASN.zip"
        zip_extract_dir = extract_dir / "geolite2_data_asn"
        super().__init__(url, zip_file_name, zip_extract_dir)
        self.ipv4_blocks = []
        self.ipv6_blocks = []

    def extract_ipv4_blocks(self, asn_list):
        self.ipv4_blocks = self.__extract_blocks(
            "GeoLite2-ASN-Blocks-IPv4.csv", asn_list
        )
        return self

    def extract_ipv6_blocks(self, asn_list):
        self.ipv6_blocks = self.__extract_blocks(
            "GeoLite2-ASN-Blocks-IPv6.csv", asn_list
        )
        return self

    def __extract_blocks(self, filename, asn_list):
        blocks = []
        csv_path = self.find(filename)
        with open(csv_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                asn = row.get("autonomous_system_number")
                if asn in asn_list:
                    network = row["network"]
                    blocks.append(netaddr.IPNetwork(network))
        logging.debug(f"Found {len(blocks)} block(s) for listed ASNs")
        return blocks


# ASNListManager


class ASNListManager(object):
    def __init__(self, url, extract_dir):
        self.output_file = extract_dir / "asn-list.txt"
        self.downloader = Downloader(url, self.output_file)

    def is_downloaded(self):
        return self.downloader.is_downloaded()

    def download(self):
        self.downloader.download()

    def parse(self):
        asn_list = []
        with open(self.output_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("AS"):
                    parts = line.split()
                    if parts:
                        asn = parts[0][2:]  # Remove 'AS' prefix
                        if asn.isdigit():
                            asn_list.append(asn)
        logging.debug(f"Extracted {len(asn_list)} AS numbers")
        return asn_list


# Writers


def merge_cidr_blocks(country_blocks_dict, asn_blocks_list):
    """
    Merges blocks from country and ASN sources, extracts unique IPs, and returns a set of unique sorted blocks.
    """
    unique_blocks = set(asn_blocks_list)
    for blocks in country_blocks_dict.values():
        unique_blocks.update(set(blocks))
    return sorted(netaddr.cidr_merge(unique_blocks))


def write_ruleset(blocks, output_file):
    """
    Aggregates blocks for each country and writes them to an Shadowrocket-compatible RULE-SET text file.
    """
    with open(output_file, "w") as f:
        aggregated_blocks = netaddr.cidr_merge(blocks)
        for block in aggregated_blocks:
            f.write(f"IP-CIDR,{block}\n")
    logging.info(f"Shadowrocket rule set saved to {output_file}")


def write_combined_ruleset(country_blocks_dict, asn_blocks_list, output_file):
    """
    Aggregates blocks for each country and ASN and writes them to an Shadowrocket-compatible RULE-SET text file.
    """
    aggregated_blocks = merge_cidr_blocks(country_blocks_dict, asn_blocks_list)
    with open(output_file, "w") as f:
        for block in aggregated_blocks:
            f.write(f"IP-CIDR,{block}\n")
    logging.info(f"Combined rule set saved to {output_file}")



# Entry point


class Command(object):
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            formatter_class=argparse.RawTextHelpFormatter
        )
        self.parser.add_argument(
            "-v", "--verbose", action="store_true", help="enable verbose output"
        )
        self.parser.add_argument(
            "-l",
            "--license-key",
            help="MaxMind license key for downloading GeoLite2 databases",
            required=True,
        )
        self.parser.add_argument(
            "-c",
            "--countries",
            nargs="+",
            help="List of country codes to include [default: %(default)s]",
            default=["RU"],
        )
        self.parser.add_argument(
            "-a",
            "--asn-list-url",
            help="URL to download ASN list of government agencies and their associated networks. [default: %(default)s]",
            default="https://raw.githubusercontent.com/C24Be/AS_Network_List/refs/heads/main/auto/all-ru-asn.txt",
        )
        self.parser.add_argument(
            "-e",
            "--extract-dir",
            help="Output directory to extract geolite files to and store intermediate files [default: %(default)s]",
            default="./extracted",
        )
        self.parser.add_argument(
            "-o",
            "--output-dir",
            help="Output directory with generated lists [default: %(default)s]",
            default="./out",
        )
        self.parser.add_argument(
            "--clean",
            action="store_true",
            help="Clean extracted files if any before running",
        )

    def get_arguments(self):
        return self.parser.parse_args()

    def help(self):
        self.parser.print_help()

    def run(self):
        args = self.get_arguments()
        log_level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(format="%(levelname)s: %(message)s", level=log_level)
        extract_dir = Path(args.extract_dir)
        if args.clean and extract_dir.exists():
            logging.debug(f"Cleaning up {extract_dir}...")
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        output_dir = Path(args.output_dir)
        if output_dir.exists():
            logging.debug(f"Cleaning up {output_dir}...")
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)

        geo_lite2_country_url = f"https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country-CSV&license_key={args.license_key}&suffix=zip"
        geo_lite2_asn_url = f"https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-ASN-CSV&license_key={args.license_key}&suffix=zip"

        geo_lite2_country_db = GeoLite2DatabaseCountry(
            geo_lite2_country_url, extract_dir
        )
        geo_lite2_asn_db = GeoLite2DatabaseASN(geo_lite2_asn_url, extract_dir)
        asn_list_manager = ASNListManager(args.asn_list_url, extract_dir)

        if not geo_lite2_country_db.is_downloaded():
            (geo_lite2_country_db.download().extract())

        if not geo_lite2_asn_db.is_downloaded():
            (geo_lite2_asn_db.download().extract())

        if not asn_list_manager.is_downloaded():
            asn_list_manager.download()

        (
            geo_lite2_country_db.extract_geoname_country_mapping()
            .extract_ipv4_blocks(args.countries)
            .extract_ipv6_blocks(args.countries)
        )

        asn_list = asn_list_manager.parse()

        (geo_lite2_asn_db.extract_ipv4_blocks(asn_list).extract_ipv6_blocks(asn_list))

        for country_code, blocks in geo_lite2_country_db.ipv4_blocks.items():
            write_ruleset(
                blocks,
                output_dir / f"maxmind_ipv4_{country_code.lower()}_geo_cidr.list",
            )

        for country_code, blocks in geo_lite2_country_db.ipv6_blocks.items():
            write_ruleset(
                blocks,
                output_dir / f"maxmind_ipv6_{country_code.lower()}_geo_cidr.list",
            )

        write_ruleset(
            geo_lite2_asn_db.ipv4_blocks, output_dir / f"maxmind_ipv4_ru_asn_cidr.list"
        )

        write_ruleset(
            geo_lite2_asn_db.ipv6_blocks, output_dir / f"maxmind_ipv6_ru_asn_cidr.list"
        )

        write_combined_ruleset(
            geo_lite2_country_db.ipv4_blocks,
            geo_lite2_asn_db.ipv4_blocks,
            output_dir / "maxmind_ipv4_all_cidr.list",
        )

        write_combined_ruleset(
            geo_lite2_country_db.ipv6_blocks,
            geo_lite2_asn_db.ipv6_blocks,
            output_dir / "maxmind_ipv6_all_cidr.list",
        )



if __name__ == "__main__":
    command = Command()
    command.run()
