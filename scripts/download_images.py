"""
Baixa imagens de todos os componentes do catálogo para frontend/public/images/.
Dependências: pip install duckduckgo_search requests Pillow
"""

import time
import requests
from io import BytesIO
from pathlib import Path
from PIL import Image
from duckduckgo_search import DDGS

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "frontend/public/images"
IMG_WIDTH, IMG_HEIGHT = 800, 520
TIMEOUT = 12
DELAY_BETWEEN = 2.5

COMPONENTS = [
    # CPUs Intel
    ("intel-i5-14600k",    "Intel Core i5-14600K processor OEM photo"),
    ("intel-i7-14700k",    "Intel Core i7-14700K processor OEM photo"),
    ("intel-i5-12400f",    "Intel Core i5-12400F processor OEM photo"),
    ("intel-i3-12100f",    "Intel Core i3-12100F processor OEM photo"),
    ("intel-i5-13400f",    "Intel Core i5-13400F processor OEM photo"),
    ("intel-i5-14400f",    "Intel Core i5-14400F processor OEM photo"),
    ("intel-i7-13700k",    "Intel Core i7-13700K processor OEM photo"),
    ("intel-i9-13900ks",   "Intel Core i9-13900KS processor OEM photo"),
    ("intel-i9-14900k",    "Intel Core i9-14900K processor OEM photo"),
    # CPUs AMD
    ("ryzen-5-5600",       "AMD Ryzen 5 5600 processor OEM photo"),
    ("ryzen-7-5700x",      "AMD Ryzen 7 5700X processor OEM photo"),
    ("ryzen-5-7600",       "AMD Ryzen 5 7600 processor OEM photo"),
    ("ryzen-7-7800x3d",    "AMD Ryzen 7 7800X3D processor OEM photo"),
    ("ryzen-9-7950x",      "AMD Ryzen 9 7950X processor OEM photo"),
    ("ryzen-3-5300g",      "AMD Ryzen 3 5300G processor OEM photo"),
    ("ryzen-5-5500",       "AMD Ryzen 5 5500 processor OEM photo"),
    ("ryzen-9-5900x",      "AMD Ryzen 9 5900X processor OEM photo"),
    ("ryzen-9-5950x",      "AMD Ryzen 9 5950X processor OEM photo"),
    ("ryzen-5-7600x",      "AMD Ryzen 5 7600X processor OEM photo"),
    ("ryzen-9-7900x",      "AMD Ryzen 9 7900X processor OEM photo"),
    ("ryzen-7-9800x3d",    "AMD Ryzen 7 9800X3D processor OEM photo"),
    ("ryzen-9-9950x",      "AMD Ryzen 9 9950X processor OEM photo"),
    # Motherboards
    ("b550-am4-ddr4",      "ASUS B550 ATX motherboard AM4 DDR4 product photo"),
    ("b550m-am4-ddr4",     "Gigabyte B550M Micro-ATX motherboard AM4 DDR4 product photo"),
    ("x570-am4-ddr4",      "MSI X570 ATX motherboard AM4 DDR4 product photo"),
    ("b650-am5-ddr5",      "ASRock B650 ATX motherboard AM5 DDR5 product photo"),
    ("x670e-am5-ddr5",     "ASUS ROG X670E ATX motherboard AM5 DDR5 product photo"),
    ("b760-lga1700-ddr5",  "Gigabyte B760 ATX motherboard LGA1700 DDR5 product photo"),
    ("z790-lga1700-ddr5",  "MSI Z790 ATX motherboard LGA1700 DDR5 product photo"),
    ("b660-lga1700-ddr4",  "ASUS B660M Micro-ATX motherboard LGA1700 DDR4 product photo"),
    # RAM
    ("ram-16gb-ddr4",      "Kingston 16GB DDR4 3200MHz memory RAM stick product photo"),
    ("ram-32gb-ddr4",      "Corsair 32GB DDR4 3600MHz memory RAM sticks product photo"),
    ("ram-16gb-ddr5",      "Kingston 16GB DDR5 5600MHz memory RAM stick product photo"),
    ("ram-32gb-ddr5",      "Corsair 32GB DDR5 6000MHz memory RAM sticks product photo"),
    ("ram-64gb-ddr5",      "G.Skill 64GB DDR5 6000MHz memory RAM sticks product photo"),
    # Storage
    ("ssd-nvme-500gb",     "WD 500GB NVMe M.2 SSD PCIe 3.0 product photo"),
    ("ssd-nvme-1tb",       "Kingston 1TB NVMe M.2 SSD PCIe 4.0 product photo"),
    ("ssd-nvme-2tb",       "Samsung 990 Pro 2TB NVMe M.2 SSD product photo"),
    # GPUs NVIDIA
    ("rtx-4060",           "NVIDIA GeForce RTX 4060 graphics card product photo"),
    ("rtx-4070-super",     "NVIDIA GeForce RTX 4070 Super graphics card product photo"),
    ("rtx-4080-super",     "NVIDIA GeForce RTX 4080 Super graphics card product photo"),
    ("rtx-5090",           "NVIDIA GeForce RTX 5090 Founders Edition graphics card product photo"),
    ("rtx-3060",           "NVIDIA GeForce RTX 3060 graphics card product photo"),
    ("rtx-3070",           "NVIDIA GeForce RTX 3070 graphics card product photo"),
    ("rtx-3080",           "NVIDIA GeForce RTX 3080 graphics card product photo"),
    ("rtx-4060-ti",        "NVIDIA GeForce RTX 4060 Ti graphics card product photo"),
    ("rtx-4070",           "NVIDIA GeForce RTX 4070 graphics card product photo"),
    ("rtx-4090",           "NVIDIA GeForce RTX 4090 Founders Edition graphics card product photo"),
    ("rtx-5070",           "NVIDIA GeForce RTX 5070 graphics card product photo"),
    ("rtx-5070-ti",        "NVIDIA GeForce RTX 5070 Ti graphics card product photo"),
    ("rtx-5080",           "NVIDIA GeForce RTX 5080 graphics card product photo"),
    # GPUs AMD
    ("rx-7600",            "AMD Radeon RX 7600 graphics card product photo"),
    ("rx-7800-xt",         "AMD Radeon RX 7800 XT graphics card product photo"),
    ("rx-6600",            "AMD Radeon RX 6600 graphics card product photo"),
    ("rx-6650-xt",         "AMD Radeon RX 6650 XT graphics card product photo"),
    ("rx-7700-xt",         "AMD Radeon RX 7700 XT graphics card product photo"),
    ("rx-7900-gre",        "AMD Radeon RX 7900 GRE graphics card product photo"),
    ("rx-7900-xtx",        "AMD Radeon RX 7900 XTX graphics card product photo"),
    # PSUs
    ("fonte-650w",         "Corsair 650W 80 Plus Bronze power supply PSU product photo"),
    ("fonte-750w",         "XPG 750W 80 Plus Gold modular power supply PSU product photo"),
    ("fonte-850w",         "Cooler Master 850W 80 Plus Gold power supply PSU product photo"),
    ("fonte-1000w",        "Corsair 1000W 80 Plus Gold modular power supply PSU product photo"),
    ("fonte-1200w",        "Seasonic 1200W 80 Plus Platinum full modular power supply PSU product photo"),
    # Cases
    ("gabinete-atx",              "Montech ATX Mid Tower PC case tempered glass product photo"),
    ("gabinete-micro-atx",        "Micro-ATX Mini Tower PC case product photo"),
    ("gabinete-compacto-itx",     "Cooler Master Mini-ITX compact PC case product photo"),
    ("gabinete-lian-li-lancool",  "Lian Li Lancool 216 PC case product photo"),
    ("gabinete-nzxt-h510",        "NZXT H510 Mid Tower PC case product photo"),
    ("gabinete-phanteks-p360a",   "Phanteks Eclipse P360A Mid Tower PC case product photo"),
    # Coolers
    ("cooler-cm-hyper212",        "Cooler Master Hyper 212 Black CPU air cooler product photo"),
    ("cooler-deepcool-ak400",     "DeepCool AK400 CPU air cooler product photo"),
    ("cooler-deepcool-ak620",     "DeepCool AK620 CPU air cooler dual tower product photo"),
    ("cooler-noctua-nhd15",       "Noctua NH-D15 CPU air cooler product photo"),
    ("cooler-liquid-120mm",       "Cooler Master MasterLiquid 120mm AIO liquid cooler product photo"),
    ("cooler-liquid-240mm",       "Cooler Master MasterLiquid 240mm AIO liquid cooler product photo"),
    ("cooler-nzxt-kraken-240",    "NZXT Kraken 240 AIO liquid cooler product photo"),
    ("cooler-nzxt-kraken-360",    "NZXT Kraken 360 AIO liquid cooler product photo"),
    ("cooler-corsair-h150i",      "Corsair iCUE H150i Elite 360mm AIO liquid cooler product photo"),
    # Kits de Memória
    ("kit-ram-16gb-ddr4-3200",    "Corsair Vengeance LPX 16GB 2x8GB DDR4 3200MHz RAM kit product photo"),
    ("kit-ram-32gb-ddr4-3600",    "G.Skill Ripjaws V 32GB 2x16GB DDR4 3600MHz RAM kit product photo"),
    ("kit-ram-64gb-ddr4-3200",    "Kingston Fury Beast 64GB 2x32GB DDR4 3200MHz RAM kit product photo"),
    ("kit-ram-32gb-ddr5-6000",    "G.Skill Trident Z5 32GB 2x16GB DDR5 6000MHz RAM kit product photo"),
    ("kit-ram-64gb-ddr5-6000",    "Corsair Dominator Platinum 64GB 2x32GB DDR5 6000MHz RAM kit product photo"),
    ("kit-ram-96gb-ddr5-6400",    "G.Skill Trident Z5 Royal 96GB 2x48GB DDR5 6400MHz RAM kit product photo"),
    # RAM adicional
    ("ram-8gb-ddr4",              "Crucial 8GB DDR4 3200MHz RAM memory stick product photo"),
    ("ram-8gb-ddr5",              "Kingston Fury Beast 8GB DDR5 4800MHz RAM memory product photo"),
    # Storage adicional
    ("ssd-sata-480gb",            "Kingston A400 480GB SATA SSD 2.5 inch product photo"),
    ("ssd-sata-1tb",              "Crucial MX500 1TB SATA SSD 2.5 inch product photo"),
    ("hdd-1tb",                   "Seagate Barracuda 1TB 7200RPM HDD hard drive product photo"),
    ("hdd-2tb",                   "WD Blue 2TB 7200RPM HDD hard drive product photo"),
    ("hdd-4tb",                   "Seagate Barracuda 4TB HDD hard drive product photo"),
    ("ssd-nvme-4tb",              "Samsung 990 Pro 4TB NVMe M.2 SSD product photo"),
    # Fontes adicionais
    ("fonte-550w",                "XPG 550W 80 Plus Bronze power supply PSU product photo"),
    ("fonte-1100w",               "Corsair 1100W 80 Plus Gold modular power supply PSU product photo"),
]


def _try_download(url: str, output_path: Path) -> bool:
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, timeout=TIMEOUT, headers=headers)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    img = img.resize((IMG_WIDTH, IMG_HEIGHT), Image.LANCZOS)
    img.save(output_path, "JPEG", quality=85, optimize=True)
    return True


def download_component(component_id: str, query: str) -> bool:
    output_path = OUTPUT_DIR / f"{component_id}.jpg"
    if output_path.exists():
        print(f"  [SKIP] {component_id} — já existe")
        return True

    print(f"  [BUSCA] {component_id}: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=8))
    except Exception as e:
        print(f"  [ERRO busca] {component_id}: {e}")
        return False

    for result in results:
        url = result.get("image", "")
        if not url:
            continue
        try:
            if _try_download(url, output_path):
                print(f"  [OK] {component_id}")
                return True
        except Exception:
            continue

    print(f"  [FALHA] {component_id} — nenhuma imagem disponível")
    return False


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(COMPONENTS)
    ok, skipped, failed = 0, 0, []

    print(f"Iniciando download de {total} imagens → {OUTPUT_DIR}\n")

    for i, (component_id, query) in enumerate(COMPONENTS, 1):
        print(f"[{i:02d}/{total}]", end=" ")
        output_path = OUTPUT_DIR / f"{component_id}.jpg"

        if output_path.exists():
            skipped += 1
            print(f"  [SKIP] {component_id} — já existe")
            continue

        success = download_component(component_id, query)
        if success:
            ok += 1
        else:
            failed.append(component_id)

        if i < total:
            time.sleep(DELAY_BETWEEN)

    print(f"\n{'='*50}")
    print(f"Concluído: {ok} baixadas, {skipped} ignoradas, {len(failed)} falhas")
    if failed:
        print("Falhas:")
        for fid in failed:
            print(f"  - {fid}")


if __name__ == "__main__":
    main()
