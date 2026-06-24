#!/usr/bin/env python3
"""Gemini Web - generate and download HD images/videos"""
import os, sys, time, json, base64, urllib.request
from playwright.sync_api import sync_playwright

CHROME_PROFILE = os.path.expanduser("~/.config/google-chrome")
OUT_DIR = os.path.expanduser("~/.openclaw/workspace/openclaw-helper/.gemini-web/output")
os.makedirs(OUT_DIR, exist_ok=True)

def generate(prompt, media_type="image", aspect="landscape", ref_image=None):
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE,
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1920, "height": 1080},
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        target = "https://gemini.google.com/videos" if media_type == "video" else "https://gemini.google.com/images"
        print(f"Opening {target}...")
        page.goto(target, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        
        if "Sign in" in page.inner_text("body") and "Gemini" not in page.inner_text("body")[:150]:
            print("NOT LOGGED IN")
            context.close()
            return
        print("OK")
        
        # Close overlays
        page.evaluate("""() => {
            var b = document.querySelectorAll('.cdk-overlay-backdrop, .cdk-overlay-container');
            b.forEach(e => e.remove());
        }""")
        
        # Model to 3.1 Pro
        print("Model: 3.1 Pro...")
        try:
            for sel in ['button[aria-label*="Model"]', 'button:has-text("Pro")', 'button:has-text("Flash")']:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    page.evaluate("el => el.click()", btn)
                    page.wait_for_timeout(1500)
                    break
            for sel2 in ['text="Gemini 3.1 Pro"', 'text="3.1 Pro"', '[role="option"]:has-text("3.1 Pro")']:
                opt = page.query_selector(sel2)
                if opt:
                    page.evaluate("el => el.click()", opt)
                    page.wait_for_timeout(500)
                    break
        except:
            pass
        page.evaluate("""() => {
            var b = document.querySelectorAll('.cdk-overlay-backdrop');
            b.forEach(e => e.remove());
        }""")
        page.wait_for_timeout(300)
        
        # Aspect ratio
        print(f"Aspect: {aspect}...")
        try:
            target_aspect = "Landscape (16:9)" if aspect == "landscape" else "Portrait (9:16)"
            for a_sel in [f'text="{target_aspect}"', f'button:has-text("{target_aspect}")', 
                          f'button:has-text("{aspect.capitalize()}")']:
                a_opt = page.query_selector(a_sel)
                if a_opt and a_opt.is_visible():
                    page.evaluate("el => el.click()", a_opt)
                    page.wait_for_timeout(500)
                    break
        except:
            pass
        page.evaluate("""() => {
            var b = document.querySelectorAll('.cdk-overlay-backdrop');
            b.forEach(e => e.remove());
        }""")
        page.wait_for_timeout(300)
        
        # Upload reference image for video
        if ref_image and os.path.exists(ref_image):
            print(f"Uploading reference: {ref_image}")
            try:
                fi = page.query_selector('input[type="file"]')
                if fi:
                    fi.set_input_files(ref_image)
                    page.wait_for_timeout(2000)
            except:
                pass
        
        # Send prompt
        page.wait_for_selector('[contenteditable="true"]', timeout=10000)
        page.evaluate("""() => {
            var input = document.querySelector('[contenteditable="true"]');
            if (input) {
                input.click();
                input.focus();
            }
        }""")
        page.wait_for_timeout(200)
        page.keyboard.insert_text(prompt)
        page.wait_for_timeout(500)
        
        send_btn = page.query_selector('button[aria-label*="Send"], button:has(svg[aria-label*="send"])')
        if send_btn and send_btn.is_visible():
            page.evaluate("el => el.click()", send_btn)
        else:
            page.keyboard.press("Enter")
        print(f"Sent at {time.strftime('%H:%M:%S')}")
        
        # Wait for generation and extract media
        wait_ms = 5000 if media_type == "video" else 2000
        t0 = time.time()
        
        found = False
        for i in range(90 if media_type == "video" else 60):
            page.wait_for_timeout(wait_ms)
            elapsed = int(time.time() - t0)
            
            try:
                r = page.evaluate("""
                    () => {
                        var out = {videos: [], images: [], limit: false, gen: false, err: ''};
                        try {
                            var vids = document.querySelectorAll('video');
                            for (var v of vids) {
                                var r = v.getBoundingClientRect();
                                if (r.width > 100) {
                                    var info = {src: v.src || '', poster: v.poster || '', w: r.width, h: r.height};
                                    var ss = v.querySelectorAll('source');
                                    info.sources = [];
                                    for (var s of ss) info.sources.push({src: s.src, type: s.type});
                                    out.videos.push(info);
                                }
                            }
                            var imgs = document.querySelectorAll('img');
                            for (var i of imgs) {
                                var r = i.getBoundingClientRect();
                                if (r.width > 200 && r.height > 200 && i.src) {
                                    out.images.push({src: i.src, w: r.width, h: r.height, x: r.x, y: r.y});
                                }
                            }
                            var b = document.body.innerText || '';
                            out.limit = b.indexOf('limit resets') >= 0 || b.indexOf('limit reached') >= 0;
                            out.gen = b.indexOf('Defining') >= 0 || b.indexOf('Creating') >= 0 || b.indexOf('Generating') >= 0 || b.indexOf('generated') >= 0 || b.indexOf('ready') >= 0;
                        } catch(e) { out.err = String(e); }
                        return out;
                    }
                """)
            except Exception as e:
                print(f"  Poll {i}: evaluate error: {e}")
                page.screenshot(path=os.path.join(OUT_DIR, f"eval-error-{int(time.time())}.png"))
                continue
            
            if r.get("err"):
                print(f"  Poll {i}: JS eval err: {r['err']}")
            
            if r.get("videos") and len(r["videos"]) > 0:
                v = r["videos"][0]
                print(f"\nVideo found! at {elapsed}s")
                print(f"  Player: {v['w']}x{v['h']}")
                if v["src"] and not v["src"].startswith("blob:"):
                    print(f"  URL: {v['src'][:120]}")
                    try:
                        # Use the browser to fetch the video URL (preserves auth cookies)
                        result = page.evaluate("""async (url) => {
                            var resp = await fetch(url, {credentials: 'include'});
                            var blob = await resp.blob();
                            return await new Promise(function(resolve) {
                                var reader = new FileReader();
                                reader.onloadend = function() { resolve(reader.result); };
                                reader.readAsDataURL(blob);
                            });
                        }""", v["src"])
                        raw = result.split(",")[1] if "," in result else result
                        path = os.path.join(OUT_DIR, "gemini-video.mp4")
                        with open(path, "wb") as f:
                            f.write(base64.b64decode(raw))
                        print(f"  ✓ Downloaded ({os.path.getsize(path)} bytes): {path}")
                    except Exception as e:
                        print(f"  Download failed: {e}")
                for s in v.get("sources", []):
                    if s["src"]:
                        print(f"  Source: {s['src'][:120]}")
                        try:
                            path = os.path.join(OUT_DIR, f"gemini-video.{s['type'].split('/')[-1] or 'mp4'}")
                            urllib.request.urlretrieve(s["src"], path)
                            print(f"  ✓ Downloaded: {path}")
                        except:
                            pass
                if v.get("poster"):
                    try:
                        import urllib.request
                        path = os.path.join(OUT_DIR, "gemini-video-poster.jpg")
                        urllib.request.urlretrieve(v["poster"], path)
                        print(f"  Poster saved: {path}")
                    except:
                        pass
                
                page.screenshot(path=os.path.join(OUT_DIR, f"gemini-video-{int(time.time())}.png"), full_page=True)
                context.close()
                found = True
                break
            
            if r.get("images") and len(r["images"]) > 0:
                img = r["images"][0]
                print(f"\nImage found! at {elapsed}s ({img['w']}x{img['h']})")
                if img["src"].startswith("blob:"):
                    # Try blob fetch, fall back to screenshot
                    saved = False
                    try:
                        b64 = page.evaluate("""async (src) => {
                            var resp = await fetch(src);
                            var blob = await resp.blob();
                            return await new Promise(function(resolve) {
                                var reader = new FileReader();
                                reader.onloadend = function() { resolve(reader.result); };
                                reader.readAsDataURL(blob);
                            });
                        }""", img["src"])
                        raw = b64.split(",")[1] if "," in b64 else b64
                        path = os.path.join(OUT_DIR, f"gemini-img-{int(time.time())}.png")
                        with open(path, "wb") as f:
                            f.write(base64.b64decode(raw))
                        print(f"  ✓ Saved: {path}")
                        saved = True
                    except Exception as e:
                        print(f"  Blob fetch failed ({e}), falling back to screenshot...")
                    if not saved:
                        # Fallback: screenshot just the image element
                        try:
                            clip = {"x": img["x"], "y": img["y"], "width": img["w"], "height": img["h"]}
                            path = os.path.join(OUT_DIR, f"gemini-img-{int(time.time())}.png")
                            page.screenshot(path=path, clip=clip)
                            print(f"  ✓ Screenshot saved: {path}")
                        except Exception as e2:
                            print(f"  Clip screenshot failed ({e2}), taking full page...")
                            path = os.path.join(OUT_DIR, f"gemini-img-{int(time.time())}.png")
                            page.screenshot(path=path, full_page=True)
                            print(f"  ✓ Full page saved: {path}")
                else:
                    import urllib.request
                    path = os.path.join(OUT_DIR, f"gemini-img-{int(time.time())}.jpg")
                    urllib.request.urlretrieve(img["src"], path)
                    print(f"  ✓ Saved: {path}")
                
                page.screenshot(path=os.path.join(OUT_DIR, f"result-{int(time.time())}.png"))
                context.close()
                found = True
                break
            
            if r.get("limit"):
                print("Limit reached")
                context.close()
                return
            
            if elapsed % 10 == 0:
                s = " [gen...]" if r.get("gen") else ""
                print(f"  {elapsed}s{s}")
        
        if not found:
            print("Timeout")
            page.screenshot(path=os.path.join(OUT_DIR, f"timeout-{int(time.time())}.png"))
        context.close()

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "A futuristic city at night with flying cars"
    mt = sys.argv[2] if len(sys.argv) > 2 else "image"
    asp = sys.argv[3] if len(sys.argv) > 3 else "landscape"
    ref = sys.argv[4] if len(sys.argv) > 4 else None
    generate(p, mt, asp, ref)
