#!/usr/bin/env python3
"""
YouTube Cookie Extractor for Firefox (Linux/Pop!OS)
Extracts YouTube cookies from Firefox and creates cookies.txt for yt-dlp
"""

import os
import sys
import sqlite3
import json
import base64
from pathlib import Path
import argparse
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def find_firefox_profile():
    """Find Firefox profile directory on Linux - prioritizes profiles with cookies"""
    home = Path.home()
    
    # Common Firefox profile paths
    possible_paths = [
        home / ".mozilla" / "firefox",
        home / ".librewolf",
        home / ".waterfox",
    ]
    
    best_profile = None
    best_profile_has_cookies = False
    
    for base_path in possible_paths:
        if not base_path.exists():
            continue
            
        # Look for profiles.ini
        profiles_ini = base_path / "profiles.ini"
        if profiles_ini.exists():
            profiles = []
            
            with open(profiles_ini, 'r') as f:
                current_section = None
                for line in f:
                    line = line.strip()
                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1]
                    elif current_section and '=' in line:
                        key, value = line.split('=', 1)
                        if current_section.startswith('Profile'):
                            profiles.append({key.strip(): value.strip()})
            
            # Check each profile for cookies.sqlite
            for profile in profiles:
                if 'Path' in profile:
                    profile_path = base_path / profile['Path']
                    if profile_path.exists():
                        cookies_db = profile_path / "cookies.sqlite"
                        if cookies_db.exists() and cookies_db.stat().st_size > 0:
                            # This profile has cookies - prioritize it
                            if not best_profile_has_cookies:
                                best_profile = str(profile_path)
                                best_profile_has_cookies = True
                                logger.info(f"Found profile with cookies: {profile_path}")
                            elif 'default-release' in profile['Path'] or profile.get('Default', '0') == '1':
                                # Prefer default-release or marked as default
                                best_profile = str(profile_path)
                                logger.info(f"Using preferred profile: {profile_path}")
                        elif not best_profile_has_cookies:
                            # Fallback to any existing profile if none have cookies yet
                            if not best_profile:
                                best_profile = str(profile_path)
                                logger.info(f"Using fallback profile: {profile_path}")
            
            # If no profiles.ini or no profiles found, search directly
            if not best_profile:
                for profile_dir in base_path.glob("*.default*"):
                    if profile_dir.is_dir():
                        cookies_db = profile_dir / "cookies.sqlite"
                        if cookies_db.exists() and cookies_db.stat().st_size > 0:
                            best_profile = str(profile_dir)
                            logger.info(f"Found profile with cookies via search: {profile_dir}")
                            break
                        elif not best_profile:
                            best_profile = str(profile_dir)
                            logger.info(f"Using fallback profile via search: {profile_dir}")
                
                # If still no profile, look for any profile with places.sqlite
                if not best_profile:
                    for profile_dir in base_path.iterdir():
                        if profile_dir.is_dir() and (profile_dir / "places.sqlite").exists():
                            best_profile = str(profile_dir)
                            logger.info(f"Found profile with places.sqlite: {profile_dir}")
                            break
    
    return best_profile

def extract_youtube_cookies(profile_path, domains=None):
    """Extract YouTube cookies from Firefox SQLite database"""
    if domains is None:
        domains = ['youtube.com', 'google.com', 'accounts.google.com']
    
    cookies_db = os.path.join(profile_path, 'cookies.sqlite')
    
    if not os.path.exists(cookies_db):
        print(f"❌ Cookie database not found: {cookies_db}")
        return []
    
    # Create a temporary copy to avoid locking issues
    temp_db = f"{cookies_db}.tmp"
    try:
        import shutil
        shutil.copy2(cookies_db, temp_db)
    except Exception as e:
        print(f"❌ Failed to copy cookie database: {e}")
        return []
    
    cookies = []
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Firefox cookie table structure
        query = """
        SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite
        FROM moz_cookies 
        WHERE host LIKE ? OR host LIKE ? OR host LIKE ? OR host LIKE ? OR host LIKE ? OR host LIKE ?
        """
        
        params = []
        for domain in domains:
            params.append(f'%{domain}%')
            params.append(f'.{domain}%')
        
        cursor.execute(query, params)
        
        for row in cursor.fetchall():
            name, value, host, path, expiry, is_secure, is_http_only, same_site = row
            
            # Skip cookies with no name or value
            if not name or not value:
                continue
            
            # Convert to yt-dlp format
            cookie = {
                'name': name,
                'value': value,
                'domain': host,
                'path': path,
                'expires': expiry if expiry > 0 else None,
                'secure': bool(is_secure),
                'httpOnly': bool(is_http_only),
            }
            
            # Handle sameSite (Firefox 63+)
            if same_site is not None:
                same_site_map = {0: 'unspecified', 1: 'lax', 2: 'strict', 3: 'none'}
                cookie['sameSite'] = same_site_map.get(same_site, 'unspecified')
            
            cookies.append(cookie)
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error reading cookie database: {e}")
        return []
    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_db)
        except:
            pass
    
    return cookies

def cookies_to_netscape(cookies, output_file):
    """Convert cookies to Netscape format for yt-dlp"""
    with open(output_file, 'w') as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# This is a generated file! Do not edit.\n")
        f.write(f"# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("#\n")
        
        for cookie in cookies:
            # Netscape format: domain \t flag \t path \t secure \t expiration \t name \t value
            domain_flag = "TRUE" if cookie['domain'].startswith('.') else "FALSE"
            secure_flag = "TRUE" if cookie['secure'] else "FALSE"
            expiration = str(int(cookie['expires'])) if cookie['expires'] else "0"
            
            line = f"{cookie['domain']}\t{domain_flag}\t{cookie['path']}\t{secure_flag}\t{expiration}\t{cookie['name']}\t{cookie['value']}\n"
            f.write(line)

def cookies_to_json(cookies, output_file):
    """Convert cookies to JSON format"""
    with open(output_file, 'w') as f:
        json.dump(cookies, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description='Extract YouTube cookies from Firefox')
    parser.add_argument('--profile', help='Firefox profile path (auto-detected if not specified)')
    parser.add_argument('--output', '-o', default='cookies.txt', help='Output file (default: cookies.txt)')
    parser.add_argument('--format', choices=['netscape', 'json'], default='netscape', help='Output format')
    parser.add_argument('--domains', nargs='+', default=['youtube.com', 'google.com', 'accounts.google.com'], 
                       help='Domains to extract cookies for')
    parser.add_argument('--list-profiles', action='store_true', help='List available Firefox profiles')
    
    args = parser.parse_args()
    
    if args.list_profiles:
        print("🔍 Searching for Firefox profiles...")
        profile_path = find_firefox_profile()
        if profile_path:
            print(f"✅ Found profile: {profile_path}")
        else:
            print("❌ No Firefox profiles found")
            print("💡 Make sure Firefox is installed and has been used at least once")
        return
    
    # Find Firefox profile
    if args.profile:
        profile_path = args.profile
        if not os.path.exists(profile_path):
            print(f"❌ Profile path does not exist: {profile_path}")
            sys.exit(1)
    else:
        print("🔍 Searching for Firefox profile...")
        profile_path = find_firefox_profile()
        
        if not profile_path:
            print("❌ No Firefox profile found")
            print("💡 Please specify the profile path with --profile")
            print("💡 Or make sure Firefox is installed and has been used")
            sys.exit(1)
    
    print(f"📁 Using Firefox profile: {profile_path}")
    
    # Check if cookies.sqlite exists
    cookies_db = os.path.join(profile_path, 'cookies.sqlite')
    if not os.path.exists(cookies_db):
        print(f"❌ Cookie database not found: {cookies_db}")
        print("💡 This profile doesn't have a cookies database")
        print("💡 Try another profile with: --profile /path/to/other/profile")
        sys.exit(1)
    
    print(f"✅ Found cookie database: {cookies_db}")
    print(f"📊 Database size: {os.path.getsize(cookies_db)} bytes")
    
    # Close Firefox to prevent database locking
    print("⚠️  Make sure Firefox is closed to prevent database locking")
    input("Press Enter to continue (or Ctrl+C to cancel)...")
    
    # Extract cookies
    print("🍪 Extracting cookies...")
    cookies = extract_youtube_cookies(profile_path, args.domains)
    
    if not cookies:
        print("❌ No cookies found for the specified domains")
        print("💡 Make sure you're logged into YouTube in Firefox")
        sys.exit(1)
    
    print(f"✅ Found {len(cookies)} cookies")
    
    # Filter for essential YouTube cookies
    essential_cookies = []
    for cookie in cookies:
        # Essential cookies for YouTube authentication
        if any(name in cookie['name'].lower() for name in [
            'sapisid', 'hsid', 'ssid', 'apiscsid', 'login_info', 'session_token',
            'visitor_id', 'ytc', 'pref', 'consession', 'sid', 'hl', 'gl'
        ]):
            essential_cookies.append(cookie)
    
    print(f"🎯 Found {len(essential_cookies)} essential YouTube cookies")
    
    # Save cookies
    if args.format == 'netscape':
        cookies_to_netscape(essential_cookies, args.output)
        print(f"✅ Cookies saved to: {args.output} (Netscape format)")
    else:
        cookies_to_json(essential_cookies, args.output)
        print(f"✅ Cookies saved to: {args.output} (JSON format)")
    
    print("\n🎉 Cookie extraction complete!")
    print(f"📝 Use this file in your bot config: cookie_file={args.output}")
    print("\n⚠️  Keep this file secure - it contains your login credentials!")
    print("🔄 Regenerate this file periodically as cookies expire")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
