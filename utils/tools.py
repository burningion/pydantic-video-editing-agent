import subprocess
import yt_dlp

class YtDlpImpersonator:
    """A simple wrapper for yt-dlp with automatic impersonation"""
    
    def __init__(self, target_index=0):
        """
        Initialize with optional target index
        
        Args:
            target_index: Index of impersonation target to use (default: 0 for first one)
        """
        self.target = None
        self.target_index = target_index
        # Try to get targets right away
        self._get_impersonation_target()
    
    def _get_impersonation_target(self):
        """Get the impersonation target to use"""
        try:
            # Run the command to list impersonate targets
            result = subprocess.run(
                ['yt-dlp', '--list-impersonate-targets'],
                capture_output=True, text=True
            )
            
            # Extract the table part of the output
            output_lines = result.stdout.strip().split('\n')
            
            # Find where the table starts (after the header line with dashes)
            table_start = 0
            for i, line in enumerate(output_lines):
                if '----' in line:
                    table_start = i + 1
                    break
            
            # Extract the data lines
            data_lines = output_lines[table_start:]
            
            # Parse the first target (or target at specified index)
            if len(data_lines) > self.target_index:
                target_line = data_lines[self.target_index]
                parts = [p.strip() for p in target_line.split() if p.strip()]
                
                if len(parts) >= 2:
                    self.target = {
                        'client': parts[0],
                        'os': parts[1]
                    }
                    return self.target
            
            # Fallback to a default if parsing fails
            self.target = {
                'client': 'Chrome-124',
                'os': 'Macos-14'
            }
            
        except Exception as e:
            print(f"Error getting impersonate targets: {e}")
            # Fallback to a reliable default
            self.target = {
                'client': 'Chrome-99',
                'os': 'Windows-10'
            }
        
        return self.target
    
    def download(self, url, output_path=None, format='best', download=True, **extra_opts):
        """
        Download or extract info from a URL using impersonation
        
        Args:
            url: The URL to download from
            output_path: Path to save the file (optional)
            format: Format to download (default: 'best')
            download: Whether to download (True) or just extract info (False)
            **extra_opts: Additional options to pass to yt-dlp
            
        Returns:
            Video info dictionary if download=False, otherwise None
        """
        if not self.target:
            self._get_impersonation_target()
        
        # Construct the target string
        target_str = f"{self.target['client']}:{self.target['os']}"
        
        # Build options
        ydl_opts = {
            'quiet': False,
            'format': format,
            'impersonate': target_str
        }
        
        # Add output path if specified
        if output_path:
            ydl_opts['outtmpl'] = output_path
        
        # Add any extra options
        ydl_opts.update(extra_opts)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if download:
                    ydl.download([url])
                    return None
                else:
                    return ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"Error with {target_str}: {e}")
            return None
    
    def extract_info(self, url, **extra_opts):
        """
        Extract info about a URL without downloading
        
        Args:
            url: The URL to extract info from
            **extra_opts: Additional options to pass to yt-dlp
            
        Returns:
            Video info dictionary
        """
        return self.download(url, download=False, **extra_opts)


# Easy-to-use functions for direct importing

def download(url, output_path=None, format='best', **extra_opts):
    """
    Quick function to download with auto-impersonation
    
    Args:
        url: The URL to download from
        output_path: Path to save the file (optional)
        format: Format to download (default: 'best')
        **extra_opts: Additional options to pass to yt-dlp
    """
    impersonator = YtDlpImpersonator()
    return impersonator.download(url, output_path, format, True, **extra_opts)

def extract_info(url, **extra_opts):
    """
    Quick function to extract info with auto-impersonation
    
    Args:
        url: The URL to extract info from
        **extra_opts: Additional options to pass to yt-dlp
        
    Returns:
        Video info dictionary
    """
    impersonator = YtDlpImpersonator()
    return impersonator.extract_info(url, **extra_opts)