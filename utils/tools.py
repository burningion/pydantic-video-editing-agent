import subprocess
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

class YtDlpImpersonator:
    """A wrapper for yt-dlp with automatic impersonation"""
    
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
                
                if len(parts) >= 3:  # Client OS Source format
                    client_parts = parts[0].split('-', 1)
                    client = client_parts[0]
                    version = client_parts[1] if len(client_parts) > 1 else None
                    
                    os_parts = parts[1].split('-', 1)
                    os_name = os_parts[0]
                    os_version = os_parts[1] if len(os_parts) > 1 else None
                    
                    return ImpersonateTarget(
                        client=client,
                        version=version,
                        os=os_name,
                        os_version=os_version
                    )
            
            # Fallback to a default Chrome target
            return ImpersonateTarget(
                client="Chrome",
                version="99",
                os="Windows",
                os_version="10"
            )
            
        except Exception as e:
            print(f"Error getting impersonate targets: {e}")
            # Fallback to a reliable default
            return ImpersonateTarget(
                client="Chrome",
                version="99",
                os="Windows",
                os_version="10"
            )
    
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
            self.target = self._get_impersonation_target()
        
        # Build options
        ydl_opts = {
            'quiet': False,
            'format': format,
            # Simplify impersonation to just use browser name
            'impersonate': self.target.client + (f"-{self.target.version}" if self.target.version else "")
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
            print(f"Error: {e}")
            # Fall back to command-line approach if API approach fails
            return self._fallback_download(url, output_path, format, download, **extra_opts)
    
    def _fallback_download(self, url, output_path=None, format='best', download=True, **extra_opts):
        """Fallback method using subprocess if the API approach fails"""
        cmd = ['yt-dlp']

        # Simplify target string to just browser name (no OS)
        target_str = f"{self.target.client}"
        if self.target.version:
            target_str += f"-{self.target.version}"
        cmd.extend(['--impersonate', target_str])

        # Add format
        cmd.extend(['-f', format])
        
        # Add output template if specified
        if output_path:
            cmd.extend(['-o', output_path])
            
        # Add dump-json if just extracting info
        if not download:
            cmd.append('--dump-json')
            cmd.append('--no-download')
        
        # Add URL
        cmd.append(url)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Command failed: {result.stderr}")
                return None
            
            if not download:
                import json
                try:
                    return json.loads(result.stdout)
                except:
                    print(f"Failed to parse JSON: {result.stdout[:100]}...")
                    return None
            
            return True
        except Exception as e:
            print(f"Fallback method failed: {e}")
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
    
    def list_available_targets(self):
        """List all available impersonation targets"""
        result = subprocess.run(
            ['yt-dlp', '--list-impersonate-targets'],
            capture_output=False, text=True
        )
        return result.stdout if result.returncode == 0 else None


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

def list_impersonate_targets():
    """List all available impersonation targets"""
    impersonator = YtDlpImpersonator()
    impersonator.list_available_targets()