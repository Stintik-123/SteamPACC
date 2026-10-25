# SteamPACC (English)

**SteamPACC** (Steam Price and Currency Converter) shows Steam game prices in multiple currencies. Prices are embedded directly into the Steam client's store pages — like Augmented Steam, but without a browser extension.

## Features

- **Prices right in the Steam store** — a block with regional prices appears under the purchase box on any game page
- **Per-DLC prices** — a collapsible list adds a price line under each DLC
- **Any game** — detected from the open store page, not just installed ones
- **Regular app window** — status, Steam restart button, region checkboxes, dark and light themes, Russian and English UI
- **Instant apply** — changing regions updates open pages without a reload
- **16 currencies** — RUB, USD, EUR, GBP, TRY, KZT, UAH, PLN, BRL, JPY and more
- **Console mode** — `steampacc games`, `steampacc price 570`
- **Autostart** with Windows via a checkbox

## Security — read before using

SteamPACC restarts Steam with the official `-cef-enable-debugging` flag. While Steam runs with this flag, **its debug port (127.0.0.1:8080) is open without authentication**: any local program can connect to it, read Steam pages and run code in them. SteamPACC protects itself (it verifies the port belongs to Steam via User-Agent) but cannot close the port for others. Recommendations: don't keep Steam running with the flag permanently; restart it without integration when you're done comparing prices.

The one-line installer verifies SHA256 checksums (`SHA256SUMS.txt` in each release). For manual installs verify yourself:

```powershell
Get-FileHash -Algorithm SHA256 .\SteamPACC.exe
```

## Install

```powershell
irm https://raw.githubusercontent.com/Stintik-123/SteamPACC/main/installer/install.ps1 | iex
```

Or grab `SteamPACC-Setup-<version>.exe` / `SteamPACC.exe` from [Releases](https://github.com/Stintik-123/SteamPACC/releases), or `pip install git+https://github.com/Stintik-123/SteamPACC.git`.

## Usage

1. Launch SteamPACC — the window opens
2. Click **Restart Steam with prices** — Steam restarts with integration (~20 s), the app waits until ready
3. Open any game in the store — the regional price block appears
4. Pick regions in the app window → **Apply**; open pages update instantly
5. Language and theme toggles are in the same window

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE)
