# Public Google OAuth information pages

The static pages in `public/` are deployed in an isolated Nginx container. Caddy serves them at `education.rtm-app.ru` and, during the DNS transition, at `rtmgroupdocs.fvds.ru/education-next-info/`.

## DNS

`rtm-app.ru` is registered in the FirstVDS account `rtmgroupdocs@gmail.com`. Its current nameservers are `ns1.reg.ru` and `ns2.reg.ru`; the domain is not present in the unrelated REG.RU login `aiapprtm@gmail.com`.

The `rtm-app.ru` zone was created in the FirstVDS DNSmanager on 2026-11-26 with:

| Name | Type | Value |
| --- | --- | --- |
| `@` | A | `62.109.6.159` |
| `education` | A | `62.109.6.159` |

The apex currently has only a parking A record and no MX or TXT records at the old nameservers. Caddy already has an apex site for the existing Goodwin project. FirstVDS also created default wildcard A and MX records in the new zone. The registrar lists the domain as "Требуется настройка". Changing the nameservers requires the owner to complete the mandatory personal contact form; do not collect those details in the repository or chat. After that, change the nameservers to `ns1.firstvds.ru` and `ns2.firstvds.ru`. DNS propagation can take up to 72 hours. Verify the public HTTPS pages before entering the links in Google Cloud.

## Google Auth Platform → Branding

- Application home page: `https://education.rtm-app.ru/`
- Application privacy policy link: `https://education.rtm-app.ru/privacy/`
- Application terms of service link: `https://education.rtm-app.ru/terms/`
- Authorized domains: `rtm-app.ru`

Verify ownership of `rtm-app.ru` through Google Search Console with a DNS TXT record in the FirstVDS zone. Do not alter the OAuth Client ID or API permissions during the branding setup.
