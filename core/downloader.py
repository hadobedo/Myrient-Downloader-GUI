import os
import requests
import urllib.parse


class Downloader:
    """Handles downloading files and related operations."""
    
    @staticmethod
    def check_file_exists(url, local_path):
        """Check if local file exists and matches the remote file size."""
        if os.path.exists(local_path):
            local_file_size = os.path.getsize(local_path)
            
            # Get the size of the remote file
            response = requests.head(url)
            if 'content-length' in response.headers:
                remote_file_size = int(response.headers['content-length'])
                
                # If the local file is smaller, attempt to resume the download
                if local_file_size < remote_file_size:
                    print(f"Local file is smaller than the remote file. Attempting to resume download...")
                    return False
                # If the local file is the same size as the remote file, skip the download
                elif local_file_size == remote_file_size:
                    print(f"Local file is the same size as the remote file. Skipping download...")
                    return True
            else:
                print("Could not get the size of the remote file.")
                return False
        return False

    @staticmethod
    def build_download_url(base_url, filename):
        """Build a download URL by encoding the filename."""
        encoded_filename = urllib.parse.quote(filename)
        # Ensure base_url does not end with a slash, as we add one.
        return f"{base_url.rstrip('/')}/{encoded_filename}"

    @staticmethod
    def try_alternative_domains(original_platform_url, filename_for_testing):
        """
        Tries to find a working download domain for the given platform URL and filename.
        Returns a base URL (without trailing slash) for Downloader.build_download_url.
        """
        parsed_original = urllib.parse.urlparse(original_platform_url)
        original_scheme = parsed_original.scheme
        original_host = parsed_original.hostname
        
        # path_from_original is already URL-encoded if original_platform_url was.
        # e.g., /files/No-Intro/Nintendo%20-%20Game%20Boy%20Color/
        path_from_original = parsed_original.path
        
        # base_path_for_candidates will be like /files/No-Intro/Nintendo%20-%20Game%20Boy%20Color
        base_path_for_candidates = path_from_original.rstrip('/')

        # This is the base URL structure derived from the original_platform_url.
        # e.g., "https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy%20Color"
        default_candidate_base = f"{original_scheme}://{original_host}{base_path_for_candidates}"

        alternative_hosts = []
        for i in range(10):
            alternative_hosts.append(f"download{i}.mtcontent.rs")
        for i in range(10):
            alternative_hosts.append(f"cache{i}.mtcontent.rs")

        # 1. Test the original URL's structure first.
        #    This handles cases like PS3 using dlX.myrient.erista.me which might be direct.
        if original_host:
            test_url_original = Downloader.build_download_url(default_candidate_base, filename_for_testing)
            try:
                response = requests.head(test_url_original, timeout=2, allow_redirects=True)
                if response.status_code == 200:
                    return default_candidate_base
            except requests.exceptions.RequestException:
                pass # Continue to mtcontent.rs alternatives

        # 2. Try alternative mtcontent.rs domains.
        for alt_host in alternative_hosts:
            # candidate_dl_base will be like "https://downloadX.mtcontent.rs/files/No-Intro/Nintendo%20-%20Game%20Boy%20Color"
            candidate_dl_base = f"https://{alt_host}{base_path_for_candidates}"
            test_url_alt = Downloader.build_download_url(candidate_dl_base, filename_for_testing)
            try:
                response = requests.head(test_url_alt, timeout=1.5, allow_redirects=True)
                if response.status_code == 200:
                    return candidate_dl_base # Return the base part, e.g., https://downloadX.mtcontent.rs/path
            except requests.exceptions.RequestException:
                continue
        
        # 3. Fallback to the original URL structure if no alternatives worked.
        return default_candidate_base

    @staticmethod
    def get_base_name(filename):
        """Get the base name of a file (without extension)."""
        return os.path.splitext(filename)[0]
