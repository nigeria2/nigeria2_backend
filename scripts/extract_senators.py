"""Build the 10th National Assembly senators dataset -> backend/app/senators_data.py.

TEMPLATE is the authoritative per-seat source (state | district | name | party).
LIST_ATTRS adds age / gender / terms, merged only where the names clearly match
(one name's tokens are a subset of the other), so no attribute is misattributed.

Run:  python backend/scripts/extract_senators.py
"""
import pathlib
import re

OUT = pathlib.Path(__file__).resolve().parent.parent / "app" / "senators_data.py"

# state | district | name | party   (10th NASS, 2023-2027)
TEMPLATE = """
Abia|Central|Austin Akobundu|PDP
Abia|North|Orji Uzor Kalu|APC
Abia|South|Enyinnaya Abaribe|APGA
Adamawa|Central|Aminu Iya Abbas|PDP
Adamawa|North|Amos Yohanna|PDP
Adamawa|South|Binos Dauda Yaroe|PDP
Akwa Ibom|North East|Aniekan Bassey|PDP
Akwa Ibom|North West|Godswill Akpabio|APC
Akwa Ibom|South|Ekong Sampson|PDP
Anambra|Central|Victor Umeh|LP
Anambra|North|Tony Nwoye|LP
Anambra|South|Ifeanyi Ubah|YPP
Bauchi|Central|Abdul Ningi|PDP
Bauchi|North|Samaila Dahuwa Kaila|PDP
Bauchi|South|Shehu Buba Umar|APC
Bayelsa|Central|Konbowei Benson|PDP
Bayelsa|East|Benson Agadaga|PDP
Bayelsa|West|Henry Seriake Dickson|PDP
Benue|North East|Emmanuel Udende|APC
Benue|North West|Titus Zam|APC
Benue|South|Abba Moro|PDP
Borno|Central|Kaka Shehu Lawan|APC
Borno|North|Mohammed Tahir Monguno|APC
Borno|South|Mohammed Ali Ndume|APC
Cross River|Central|Eteng Williams|PDP
Cross River|North|Agom Jarigbe|PDP
Cross River|South|Asuquo Ekpenyong|APC
Delta|Central|Ede Dafinone|APC
Delta|North|Ned Nwoko|PDP
Delta|South|Joel-Onowakpo Thomas|APC
Ebonyi|Central|Kenneth Eze|APC
Ebonyi|North|Onyekachi Nwebonyi|APC
Ebonyi|South|Anthony Ani Okorie|APC
Edo|Central|Monday Okpebholo|APC
Edo|North|Adams Oshiomhole|APC
Edo|South|Neda Imasuen|APC
Ekiti|Central|Michael Opeyemi Bamidele|APC
Ekiti|North|Cyril Fasuyi|APC
Ekiti|South|Adeyemi Adaramodu|APC
Enugu|East|Kelvin Chukwu|LP
Enugu|North|Okechukwu Ezea|LP
Enugu|West|Osita Ngwu|PDP
FCT|FCT|Ireti Kingibe|LP
Gombe|Central|Danjuma Goje|APC
Gombe|North|Ibrahim Hassan Dankwambo|PDP
Gombe|South|Anthony Siyako Yaro|PDP
Imo|East|Ezenwa Onyewuchi|LP
Imo|North|Patrick Ndubueze|APC
Imo|West|Osita Izunaso|APC
Jigawa|North East|Ahmed Abdulhamid Mallam Madori|APC
Jigawa|North West|Babangida Hussaini|APC
Jigawa|South West|Mustapha Khabeeb|PDP
Kaduna|Central|Lawal Adamu Usman|PDP
Kaduna|North|Ibrahim Khalid Mustapha|PDP
Kaduna|South|Sunday Marshall Katung|PDP
Kano|Central|Rufai Hanga|NNPP
Kano|North|Barau Jibrin|APC
Kano|South|Kawu Sumaila|APC
Katsina|Central|Abdulaziz Musa Yar'adua|APC
Katsina|North|Nasiru Sani Zangon Daura|APC
Katsina|South|Muntari Mohammed Dandutse|APC
Kebbi|Central|Adamu Aliero|PDP
Kebbi|North|Yahaya Abubakar Abdullahi|PDP
Kebbi|South|Garba Musa|APC
Kogi|Central|Natasha Akpoti-Uduaghan|PDP
Kogi|East|Jibrin Isah|APC
Kogi|West|Sunday Karimi|APC
Kwara|Central|Saliu Mustapha|APC
Kwara|North|Sadiq Suleiman Umar|APC
Kwara|South|Ashiru Oyelola Yisa|APC
Lagos|Central|Wasiu Eshinlokun-Sanni|APC
Lagos|East|Tokunbo Abiru|APC
Lagos|West|Oluranti Adebule|APC
Nasarawa|North|Godiya Akwashiki|SDP
Nasarawa|South|Mohammed Ogoshi Onawo|PDP
Nasarawa|West|Ahmed Aliyu Wadada|SDP
Niger|East|Mohammed Sani Musa|APC
Niger|North|Abubakar Sani Bello|APC
Niger|South|Peter Ndalikali Jiya|PDP
Ogun|Central|Shuaibu Salisu|APC
Ogun|East|Gbenga Daniel|APC
Ogun|West|Solomon Olamilekan Adeola|APC
Ondo|Central|Adeniyi Adegbonmire|APC
Ondo|North|Olajide Ipinsagba|APC
Ondo|South|Jimoh Ibrahim|APC
Osun|Central|Olubiyi Fadeyi|PDP
Osun|East|Francis Fadahunsi|PDP
Osun|West|Lere Oyewumi|PDP
Oyo|Central|Yunus Akintunde|APC
Oyo|North|Abdulfatai Buhari|APC
Oyo|South|Sharafadeen Alli|APC
Plateau|Central|Diket Plang|APC
Plateau|North|Pam Dachungyang|ADP
Plateau|South|Simon Lalong|APC
Rivers|East|Allwell Onyeso|PDP
Rivers|South East|Barry Mpigi|PDP
Rivers|West|Ipalibo Banigo|PDP
Sokoto|North|Aliyu Wamakko|APC
Sokoto|East|Ibrahim Gobir|APC
Sokoto|South|Aminu Tambuwal|PDP
Taraba|Central|Haruna Manu|PDP
Taraba|North|Shuaibu Isa Lau|PDP
Taraba|South|David Jimkuta|APC
Yobe|East|Ibrahim Gaidam|APC
Yobe|North|Ahmed Lawan|APC
Yobe|South|Ibrahim Mohammed Bomai|APC
Zamfara|Central|Ikra Aliyu Bilbis|PDP
Zamfara|North|Sahabi Yau|APC
Zamfara|West|Abdulaziz Abubakar Yari|APC
"""

# name | gender | age | terms
LIST_ATTRS = """
Enyinnaya Harcourt Abaribe|M|71|6
Ahmed Mallam Madori Abdulhamid|M|60|1
Adetokunbo Mukhail Abiru|M|62|1
Yari Abdulaziz Abubakar|M|57|1
Oluranti Idiat Adebule|F|56|2
Ayodele Adeniyi Adegbonmire|M|58|1
Solomon Olamilekan Adeola|M|57|4
Sunday Benson Agadaga|M|70|1
Abiodun Yunus Akintunde|M|64|1
Godswill Obot Akpabio|M|64|3
Sampson Ekong Akpan|M|59|1
Godiya Akwashiki|M|53|1
Muhammad Adamu Mainasara Aliero|M|69|7
Ahmed Wadada Aliyu|M|61|1
Abiodun Sharafadeen Alli|M|63|1
Napoleon Binkap Bali|M|62|1
Michael Opeyemi Bamidele|M|63|5
Ipalibo Banigo|F|74|3
Jibrin Ibrahim Barau|M|67|3
Etim Aniekan Bassey|M|47|1
Konbowei Friday Benson|M|64|1
Abdulfatai Omotayo Buhari|M|61|3
Omueya Ede Dafinone|M|64|1
Hassan Ibrahim Dankwambo|M|64|3
Nasiru Sani Zangon Daura|M|58|3
Henry Seriake Dickson|M|60|2
Asuquo Ekpenyong|M|49|1
Wasiu Sanni Eshinlokun||65|2
Emeka Kenneth Eze|M|56|1
Okechukwu Ezea|M|62|1
Francis Adenigba Fadahunsi|M|74|2
Olubiyi Oluwole Fadeyi|M|57|1
Cyril Oluwole Fasuyi|M|61|1
Ibrahim Gaidam|M|70|2
Mohammed Danjuma Goje|M|74|6
Uba Babangida Hussaini|M|62|1
Bernards Neda Imasuen|M|69|1
Olajide Emmanuel Ipinsagba|M|62|1
Lau Shuaibu Isa|M|65|1
Jibrin Isah|M|66|2
Cliff Elisha Ishaku|M|46|1
Aminu Iya Abbas|M|53|2
Bonaventure Osita Izunaso|M|59|3
Jarigbe Agom Jarigbe|M|56|3
Folorunsho Ibrahim Jimoh|M|59|1
Ndalikali Peter Jiya|M|68|1
Ewomazino Thomas Joel-Onowakpo|M|59|1
Dahuwa Samaila Kaila|M|64|1
Orji Uzor Kalu|M|66|4
Sunday Marshall Katung|M|65|2
Abdurrahman Suleiman Kawu|M|58|1
Mustapha Khabeeb|M|76|3
Mustapha Ibrahim Khalid|M|61|1
Heebah Ireti Kingibe|F|72|1
Ahmed Ibrahim Lawan|M|67|6
Shehu Kaka Lawan|M|51|1
Haruna Manu|M|53|3
Mohammed Tahir Monguno|M|60|5
Abba Patrick Moro|M|68|3
Barinada Barry Mpigi|M|65|4
Dandutse Mohammed Muntari|M|60|3
Garba Musa|M|65|1
Mohammed Sani Musa|M|61|2
Saliu Mustapha|M|53|1
Simon Davou Mwadkwon|M|58|3
Chiwuba Patrick Ndubueze|M|63|1
Mohammed Ali Ndume|M|67|6
Osita Ngwu|M|48|1
Abdul Ahmed Ningi|M|66|5
Peter Onyeka Nwebonyi|M|45|1
Munir Chinedu Nwoko|M|65|1
Okechukwu Tony Nwoye|M|51|1
Monday Okpebholo|M|56|1
Mohammed Ogoshi Onawo|M|74|3
Allwell Onyesoh|M|65|1
Ezenwa Francis Onyewuchi|M|58|4
Adams Aliyu Oshiomhole|M|74|3
Olalere Kamorudeen Oyewumi|M|66|1
Adaramodu Adeyemi Raphael|M|63|1
Afolabi Shuaib Salisu|M|62|1
Abubakar Bello Sani|M|58|1
Ibrahim Patrick Ubah|M|55|2
Emmanuel Memga Udende|M|65|2
Buba Shehu Umar|M|49|1
Chukwunonyelu Victor Umeh|M|64|1
Adamu Lawal Usman|M|51|1
Eteng Jonah Williams|M|56|2
Sahabi Yau|M|70|1
Musa Abdulaziz Yar'adua|M|62|1
Siyako Anthony Yaro|M|63|1
Dauda Binos Yaroe|M|71|1
Ashiru Oyelola Yisa|M|71|2
Tartenger Titus Zam|M|57|1
Aminu Tambuwal|M|59|3
Aliyu Wamakko|M|71|4
Sunday Karimi|M||2
Kelvin Chukwu|M|58|1
"""

LEADERSHIP = {"godswill akpabio": "Senate President", "barau jibrin": "Deputy Senate President"}


def tokens(name: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", name.lower())) - {"dr", "sen", "alhaji", "chief"}


def main():
    attrs = []
    for line in LIST_ATTRS.strip().splitlines():
        name, g, age, terms = line.split("|")
        attrs.append((tokens(name), g, age, terms))

    def match(nm):
        t = tokens(nm)
        for at, g, age, terms in attrs:
            if len(t & at) >= 2 and (t <= at or at <= t):
                return g, age, terms
        return "", "", ""

    rows = []
    matched = 0
    for line in TEMPLATE.strip().splitlines():
        state, district, name, party = line.split("|")
        g, age, terms = match(name)
        if g or age or terms:
            matched += 1
        lead = LEADERSHIP.get(name.lower(), "")
        rows.append({
            "name": name, "state": state, "district": district, "party": party,
            "gender": {"M": "Male", "F": "Female"}.get(g, ""),
            "age": int(age) if age else None, "terms": int(terms) if terms else None,
            "leadership": lead,
        })

    lines = ['"""10th National Assembly senators (2023-2027). Auto-generated by',
             "backend/scripts/extract_senators.py. Do not edit by hand.", '"""', "", "SENATORS = ["]
    for r in rows:
        lines.append(f"    {r!r},")
    lines.append("]")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"senators: {len(rows)} | with age/gender/terms: {matched}")
    print(f"leadership: {[r['name'] for r in rows if r['leadership']]}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
