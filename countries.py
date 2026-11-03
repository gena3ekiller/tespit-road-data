#!/usr/bin/env python3
"""The world's packs: one per Geofabrik extract (some extracts are merged into one pack, some packs cover
several countries). The app lists them by continent with the names and flags of `countries`.

countries.py              print the table
countries.py --matrix     the GitHub Actions matrix as JSON (all packs)
countries.py --matrix CH,LI
"""
import json
import sys

# Continents in the app's order.
CONTINENTS = ('europe', 'north-america', 'south-america', 'asia', 'oceania', 'africa')

# pack id (two letters, written into the pack's header), continent, Geofabrik paths, ISO codes covered.
REGIONS = [
    # Europe (Geofabrik's Europe and Russia)
    ('AD', 'europe', ['europe/andorra'], ['AD']),
    ('AL', 'europe', ['europe/albania'], ['AL']),
    ('AT', 'europe', ['europe/austria'], ['AT']),
    ('BA', 'europe', ['europe/bosnia-herzegovina'], ['BA']),
    ('BE', 'europe', ['europe/belgium'], ['BE']),
    ('BG', 'europe', ['europe/bulgaria'], ['BG']),
    ('BY', 'europe', ['europe/belarus'], ['BY']),
    ('CH', 'europe', ['europe/switzerland'], ['CH']),
    ('CY', 'europe', ['europe/cyprus'], ['CY']),
    ('CZ', 'europe', ['europe/czech-republic'], ['CZ']),
    ('DE', 'europe', ['europe/germany'], ['DE']),
    ('DK', 'europe', ['europe/denmark'], ['DK']),
    ('EE', 'europe', ['europe/estonia'], ['EE']),
    ('ES', 'europe', ['europe/spain', 'africa/canary-islands'], ['ES']),
    ('FI', 'europe', ['europe/finland'], ['FI']),
    ('FO', 'europe', ['europe/faroe-islands'], ['FO']),
    ('FR', 'europe', ['europe/france'], ['FR']),
    ('GB', 'europe', ['europe/united-kingdom'], ['GB']),
    ('GE', 'europe', ['europe/georgia'], ['GE']),
    ('GG', 'europe', ['europe/guernsey-jersey'], ['GG', 'JE']),
    ('GR', 'europe', ['europe/greece'], ['GR']),
    ('HR', 'europe', ['europe/croatia'], ['HR']),
    ('HU', 'europe', ['europe/hungary'], ['HU']),
    ('IE', 'europe', ['europe/ireland-and-northern-ireland'], ['IE']),
    ('IM', 'europe', ['europe/isle-of-man'], ['IM']),
    ('IS', 'europe', ['europe/iceland'], ['IS']),
    ('IT', 'europe', ['europe/italy'], ['IT', 'SM', 'VA']),
    ('LI', 'europe', ['europe/liechtenstein'], ['LI']),
    ('LT', 'europe', ['europe/lithuania'], ['LT']),
    ('LU', 'europe', ['europe/luxembourg'], ['LU']),
    ('LV', 'europe', ['europe/latvia'], ['LV']),
    ('MC', 'europe', ['europe/monaco'], ['MC']),
    ('MD', 'europe', ['europe/moldova'], ['MD']),
    ('ME', 'europe', ['europe/montenegro'], ['ME']),
    ('MK', 'europe', ['europe/macedonia'], ['MK']),
    ('MT', 'europe', ['europe/malta'], ['MT']),
    ('NL', 'europe', ['europe/netherlands'], ['NL']),
    ('NO', 'europe', ['europe/norway'], ['NO']),
    ('PL', 'europe', ['europe/poland'], ['PL']),
    ('PT', 'europe', ['europe/portugal', 'europe/azores'], ['PT']),
    ('RO', 'europe', ['europe/romania'], ['RO']),
    ('RS', 'europe', ['europe/serbia'], ['RS']),
    ('RU', 'europe', ['russia'], ['RU']),
    ('SE', 'europe', ['europe/sweden'], ['SE']),
    ('SI', 'europe', ['europe/slovenia'], ['SI']),
    ('SK', 'europe', ['europe/slovakia'], ['SK']),
    ('TR', 'europe', ['europe/turkey'], ['TR']),
    ('UA', 'europe', ['europe/ukraine'], ['UA']),
    ('XK', 'europe', ['europe/kosovo'], ['XK']),
    # North America, Central America and the Caribbean
    ('BS', 'north-america', ['central-america/bahamas'], ['BS']),
    ('BZ', 'north-america', ['central-america/belize'], ['BZ']),
    ('CA', 'north-america', ['north-america/canada'], ['CA']),
    ('CR', 'north-america', ['central-america/costa-rica'], ['CR']),
    ('CU', 'north-america', ['central-america/cuba'], ['CU']),
    ('DO', 'north-america', ['central-america/haiti-and-domrep'], ['DO', 'HT']),
    ('GL', 'north-america', ['north-america/greenland'], ['GL']),
    ('GP', 'north-america', ['europe/france/guadeloupe'], ['GP']),
    ('GT', 'north-america', ['central-america/guatemala'], ['GT']),
    ('HN', 'north-america', ['central-america/honduras'], ['HN']),
    ('JM', 'north-america', ['central-america/jamaica'], ['JM']),
    ('MQ', 'north-america', ['europe/france/martinique'], ['MQ']),
    ('MX', 'north-america', ['north-america/mexico'], ['MX']),
    ('NI', 'north-america', ['central-america/nicaragua'], ['NI']),
    ('PA', 'north-america', ['central-america/panama'], ['PA']),
    ('PR', 'north-america', ['north-america/us/puerto-rico'], ['PR']),
    ('SV', 'north-america', ['central-america/el-salvador'], ['SV']),
    ('US', 'north-america', ['north-america/us'], ['US']),
    ('VI', 'north-america', ['north-america/us/us-virgin-islands'], ['VI']),
    # South America
    ('AR', 'south-america', ['south-america/argentina'], ['AR']),
    ('BO', 'south-america', ['south-america/bolivia'], ['BO']),
    ('BR', 'south-america', ['south-america/brazil'], ['BR']),
    ('CL', 'south-america', ['south-america/chile'], ['CL']),
    ('CO', 'south-america', ['south-america/colombia'], ['CO']),
    ('EC', 'south-america', ['south-america/ecuador'], ['EC']),
    ('GF', 'south-america', ['europe/france/guyane'], ['GF']),
    ('GY', 'south-america', ['south-america/guyana'], ['GY']),
    ('PE', 'south-america', ['south-america/peru'], ['PE']),
    ('PY', 'south-america', ['south-america/paraguay'], ['PY']),
    ('SR', 'south-america', ['south-america/suriname'], ['SR']),
    ('UY', 'south-america', ['south-america/uruguay'], ['UY']),
    ('VE', 'south-america', ['south-america/venezuela'], ['VE']),
    # Asia
    ('AF', 'asia', ['asia/afghanistan'], ['AF']),
    ('AM', 'asia', ['asia/armenia'], ['AM']),
    ('AZ', 'asia', ['asia/azerbaijan'], ['AZ']),
    ('BD', 'asia', ['asia/bangladesh'], ['BD']),
    ('BT', 'asia', ['asia/bhutan'], ['BT']),
    ('CN', 'asia', ['asia/china'], ['CN', 'HK', 'MO']),
    ('ID', 'asia', ['asia/indonesia'], ['ID']),
    ('IL', 'asia', ['asia/israel-and-palestine'], ['IL', 'PS']),
    ('IN', 'asia', ['asia/india'], ['IN']),
    ('IQ', 'asia', ['asia/iraq'], ['IQ']),
    ('IR', 'asia', ['asia/iran'], ['IR']),
    ('JO', 'asia', ['asia/jordan'], ['JO']),
    ('JP', 'asia', ['asia/japan'], ['JP']),
    ('KG', 'asia', ['asia/kyrgyzstan'], ['KG']),
    ('KH', 'asia', ['asia/cambodia'], ['KH']),
    ('KP', 'asia', ['asia/north-korea'], ['KP']),
    ('KR', 'asia', ['asia/south-korea'], ['KR']),
    ('KZ', 'asia', ['asia/kazakhstan'], ['KZ']),
    ('LA', 'asia', ['asia/laos'], ['LA']),
    ('LB', 'asia', ['asia/lebanon'], ['LB']),
    ('LK', 'asia', ['asia/sri-lanka'], ['LK']),
    ('MM', 'asia', ['asia/myanmar'], ['MM']),
    ('MN', 'asia', ['asia/mongolia'], ['MN']),
    ('MV', 'asia', ['asia/maldives'], ['MV']),
    ('MY', 'asia', ['asia/malaysia-singapore-brunei'], ['MY', 'SG', 'BN']),
    ('NP', 'asia', ['asia/nepal'], ['NP']),
    ('PH', 'asia', ['asia/philippines'], ['PH']),
    ('PK', 'asia', ['asia/pakistan'], ['PK']),
    ('SA', 'asia', ['asia/gcc-states'], ['SA', 'AE', 'QA', 'OM', 'KW', 'BH']),
    ('SY', 'asia', ['asia/syria'], ['SY']),
    ('TH', 'asia', ['asia/thailand'], ['TH']),
    ('TJ', 'asia', ['asia/tajikistan'], ['TJ']),
    ('TL', 'asia', ['asia/east-timor'], ['TL']),
    ('TM', 'asia', ['asia/turkmenistan'], ['TM']),
    ('TW', 'asia', ['asia/taiwan'], ['TW']),
    ('UZ', 'asia', ['asia/uzbekistan'], ['UZ']),
    ('VN', 'asia', ['asia/vietnam'], ['VN']),
    ('YE', 'asia', ['asia/yemen'], ['YE']),
    # Australia and Oceania
    ('AS', 'oceania', ['australia-oceania/american-oceania'], ['AS', 'GU', 'MP']),
    ('AU', 'oceania', ['australia-oceania/australia'], ['AU']),
    ('CK', 'oceania', ['australia-oceania/cook-islands'], ['CK']),
    ('FJ', 'oceania', ['australia-oceania/fiji'], ['FJ']),
    ('FM', 'oceania', ['australia-oceania/micronesia'], ['FM']),
    ('KI', 'oceania', ['australia-oceania/kiribati'], ['KI']),
    ('MH', 'oceania', ['australia-oceania/marshall-islands'], ['MH']),
    ('NC', 'oceania', ['australia-oceania/new-caledonia'], ['NC']),
    ('NR', 'oceania', ['australia-oceania/nauru'], ['NR']),
    ('NU', 'oceania', ['australia-oceania/niue'], ['NU']),
    ('NZ', 'oceania', ['australia-oceania/new-zealand'], ['NZ']),
    ('PF', 'oceania', ['australia-oceania/polynesie-francaise'], ['PF']),
    ('PG', 'oceania', ['australia-oceania/papua-new-guinea'], ['PG']),
    ('PN', 'oceania', ['australia-oceania/pitcairn-islands'], ['PN']),
    ('PW', 'oceania', ['australia-oceania/palau'], ['PW']),
    ('SB', 'oceania', ['australia-oceania/solomon-islands'], ['SB']),
    ('TK', 'oceania', ['australia-oceania/tokelau'], ['TK']),
    ('TO', 'oceania', ['australia-oceania/tonga'], ['TO']),
    ('TV', 'oceania', ['australia-oceania/tuvalu'], ['TV']),
    ('VU', 'oceania', ['australia-oceania/vanuatu'], ['VU']),
    ('WF', 'oceania', ['australia-oceania/wallis-et-futuna'], ['WF']),
    ('WS', 'oceania', ['australia-oceania/samoa'], ['WS']),
    # Africa
    ('AO', 'africa', ['africa/angola'], ['AO']),
    ('BF', 'africa', ['africa/burkina-faso'], ['BF']),
    ('BI', 'africa', ['africa/burundi'], ['BI']),
    ('BJ', 'africa', ['africa/benin'], ['BJ']),
    ('BW', 'africa', ['africa/botswana'], ['BW']),
    ('CD', 'africa', ['africa/congo-democratic-republic'], ['CD']),
    ('CF', 'africa', ['africa/central-african-republic'], ['CF']),
    ('CG', 'africa', ['africa/congo-brazzaville'], ['CG']),
    ('CI', 'africa', ['africa/ivory-coast'], ['CI']),
    ('CM', 'africa', ['africa/cameroon'], ['CM']),
    ('CV', 'africa', ['africa/cape-verde'], ['CV']),
    ('DJ', 'africa', ['africa/djibouti'], ['DJ']),
    ('DZ', 'africa', ['africa/algeria'], ['DZ']),
    ('EG', 'africa', ['africa/egypt'], ['EG']),
    ('ER', 'africa', ['africa/eritrea'], ['ER']),
    ('ET', 'africa', ['africa/ethiopia'], ['ET']),
    ('GA', 'africa', ['africa/gabon'], ['GA']),
    ('GH', 'africa', ['africa/ghana'], ['GH']),
    ('GN', 'africa', ['africa/guinea'], ['GN']),
    ('GQ', 'africa', ['africa/equatorial-guinea'], ['GQ']),
    ('GW', 'africa', ['africa/guinea-bissau'], ['GW']),
    ('KE', 'africa', ['africa/kenya'], ['KE']),
    ('KM', 'africa', ['africa/comores'], ['KM']),
    ('LR', 'africa', ['africa/liberia'], ['LR']),
    ('LS', 'africa', ['africa/lesotho'], ['LS']),
    ('LY', 'africa', ['africa/libya'], ['LY']),
    ('MA', 'africa', ['africa/morocco'], ['MA']),
    ('MG', 'africa', ['africa/madagascar'], ['MG']),
    ('ML', 'africa', ['africa/mali'], ['ML']),
    ('MR', 'africa', ['africa/mauritania'], ['MR']),
    ('MU', 'africa', ['africa/mauritius'], ['MU']),
    ('MW', 'africa', ['africa/malawi'], ['MW']),
    ('MZ', 'africa', ['africa/mozambique'], ['MZ']),
    ('NA', 'africa', ['africa/namibia'], ['NA']),
    ('NE', 'africa', ['africa/niger'], ['NE']),
    ('NG', 'africa', ['africa/nigeria'], ['NG']),
    ('RE', 'africa', ['europe/france/reunion'], ['RE']),
    ('RW', 'africa', ['africa/rwanda'], ['RW']),
    ('SC', 'africa', ['africa/seychelles'], ['SC']),
    ('SD', 'africa', ['africa/sudan'], ['SD']),
    ('SH', 'africa', ['africa/saint-helena-ascension-and-tristan-da-cunha'], ['SH']),
    ('SL', 'africa', ['africa/sierra-leone'], ['SL']),
    ('SN', 'africa', ['africa/senegal-and-gambia'], ['SN', 'GM']),
    ('SO', 'africa', ['africa/somalia'], ['SO']),
    ('SS', 'africa', ['africa/south-sudan'], ['SS']),
    ('ST', 'africa', ['africa/sao-tome-and-principe'], ['ST']),
    ('SZ', 'africa', ['africa/swaziland'], ['SZ']),
    ('TD', 'africa', ['africa/chad'], ['TD']),
    ('TG', 'africa', ['africa/togo'], ['TG']),
    ('TN', 'africa', ['africa/tunisia'], ['TN']),
    ('TZ', 'africa', ['africa/tanzania'], ['TZ']),
    ('UG', 'africa', ['africa/uganda'], ['UG']),
    ('YT', 'africa', ['europe/france/mayotte'], ['YT']),
    ('ZA', 'africa', ['africa/south-africa'], ['ZA']),
    ('ZM', 'africa', ['africa/zambia'], ['ZM']),
    ('ZW', 'africa', ['africa/zimbabwe'], ['ZW']),
]

URL = 'https://download.geofabrik.de/{}-latest.osm.pbf'

# The largest extracts get a runner to themselves first, so the run ends sooner.
LARGE = {'US', 'RU', 'DE', 'FR', 'CA', 'GB', 'IT', 'JP', 'BR', 'PL', 'IN', 'CN', 'ES', 'ID', 'NL', 'AU'}

BY_ID = {pack: {'id': pack, 'continent': continent, 'paths': paths, 'countries': countries}
         for pack, continent, paths, countries in REGIONS}


def check():
    seen = set()
    for pack, continent, paths, countries in REGIONS:
        assert len(pack) == 2 and pack.isupper(), pack
        assert continent in CONTINENTS, (pack, continent)
        assert countries[0] == pack, pack
        for code in countries:
            assert code not in seen, code
            seen.add(code)
    assert len(BY_ID) == len(REGIONS)


def matrix(only=None):
    wanted = [BY_ID[p.strip().upper()] for p in only.split(',') if p.strip()] if only else list(BY_ID.values())
    wanted.sort(key=lambda r: (r['id'] not in LARGE, r['id']))
    return [{'id': r['id'], 'large': r['id'] in LARGE, 'urls': ' '.join(URL.format(p) for p in r['paths'])} for r in wanted]


check()

if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--matrix':
        print(json.dumps({'include': matrix(sys.argv[2] if len(sys.argv) > 2 else None)}))
    else:
        for pack, continent, paths, countries in REGIONS:
            print(pack, continent, ','.join(countries), ' + '.join(paths))
        print(len(REGIONS), 'packs,', sum(len(r[3]) for r in REGIONS), 'countries')
