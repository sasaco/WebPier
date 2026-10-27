"""The 0610 FrameWeb file of the train on both girders only (decision 102), as Example2 numbers and names it.

Example2 has no other 列車の配置: the FrameWeb tests and the acceptances that compare with it read this.
"""


_OTHER_PLACINGS = ("-2", "-3")  # the symbols of ② and ③ (decision 102); ① is "-1"
_PLACING_NAMES = ("両側の桁", "起点側の桁", "終点側の桁")


def _first_name(name):
    for placing in _PLACING_NAMES:
        name = name.removesuffix(f"　{placing}").removesuffix(f" {placing}")
    return name


def first_placing(document):
    """The 0610 FrameWeb document of the train on both girders (列車の配置 ①) only, numbered and named as Example2's,
    which has no other placing (decision 102): the load cases, Defines and Combines of ② and ③ left out, the others
    renumbered in order, the "-1" of ①'s symbols and the placing of the names dropped."""
    loads = {}
    for number, case in document["load"].items():
        if not case["symbol"].endswith(_OTHER_PLACINGS):
            loads[number] = {**case, "symbol": case["symbol"].removesuffix("-1"), "name": _first_name(case["name"])}
    load_of = {old: new for new, old in enumerate((int(n) for n in loads), 1)}
    defines = {}
    for number, row in document["define"].items():
        cases = [value for key, value in row.items() if key.startswith("C")]
        if all(abs(case) in load_of for case in cases):
            defines[number] = cases
    define_of = {old: new for new, old in enumerate((int(n) for n in defines), 1)}
    combines = {}
    for number, row in document["combine"].items():
        if row["name"].endswith(_PLACING_NAMES[1:]):
            continue
        combines[number] = {**row, "name": _first_name(row["name"])}
    combine_of = {old: new for new, old in enumerate((int(n) for n in combines), 1)}

    def renumbered(rows, number_of):
        return {str(number_of[int(number)]): {**row, "row": number_of[int(number)]} for number, row in rows.items()}

    combine_rows = {}
    for number, row in renumbered(combines, combine_of).items():
        terms = {f"C{define_of[int(key[1:])]}": value for key, value in row.items() if key.startswith("C")}
        combine_rows[number] = {key: value for key, value in row.items() if not key.startswith("C")} | terms
    pickups = {}
    for number, row in document["pickup"].items():
        members = [combine_of[value] for key, value in row.items() if key.startswith("C") and value in combine_of]
        pickups[number] = {key: value for key, value in row.items() if not key.startswith("C")} | {
            f"C{index}": member for index, member in enumerate(members, 1)}
    return {**document,
            "load": {str(load_of[int(n)]): case for n, case in loads.items()},
            "define": {str(define_of[int(n)]): {"row": define_of[int(n)], **{
                f"C{index}": (1 if case > 0 else -1) * load_of[abs(case)] for index, case in enumerate(cases, 1)}}
                for n, cases in defines.items()},
            "combine": combine_rows, "pickup": pickups}


# 0620 (decision 106): Example2's 9-14 has one loading of each check with the train and one vehicle lateral load
_EXAMPLE2_LOADINGS = {"破壊 列車最大": "複線", "破壊 車横最大": "複線", "ひび割れ 縁応力度": "複線", "ひび割れ 変動荷重": "単線",
                      "損傷 列車最大": "複線", "地盤の安定 列車最大": "複線", "地盤の安定 車横最大": "複線",
                      "短期支持 低水位": "単線", "短期支持 高水位": "単線"}
_LOADINGS = ("複線", "単線")


def example2_loading(document):
    """The 0620 FrameWeb document as Example2 numbers and names it (decision 106): of each check with the train only
    the loading Example2 has (the 複線 or 単線 of the name dropped), and one vehicle lateral load — the two tracks' (Lf2)
    left out, its Define's place in a Combine taken by the one track's (Lf1, named Lf as Example2's)."""
    single = next(number for number, case in document["load"].items() if case["symbol"] == "Lf1")
    loads = {}
    for number, case in document["load"].items():
        if case["symbol"] == "Lf2":
            double = number
            continue
        loads[number] = {**case, "symbol": "Lf", "name": "車両横荷重"} if number == single else case
    load_of = {old: new for new, old in enumerate((int(n) for n in loads), 1)}
    defines, lateral = {}, {}
    for number, row in document["define"].items():
        cases = [value for key, value in row.items() if key.startswith("C")]
        if abs(cases[0]) == int(double):
            lateral["double"] = int(number)
            continue
        if abs(cases[0]) == int(single):
            lateral["single"] = int(number)
        defines[number] = cases
    define_of = {old: new for new, old in enumerate((int(n) for n in defines), 1)}
    define_of[lateral["double"]] = define_of[lateral["single"]]
    combines = {}
    for number, row in document["combine"].items():
        name = row["name"]
        for loading in _LOADINGS:
            if name.endswith(f" {loading}"):
                base = name.removesuffix(f" {loading}")
                if _EXAMPLE2_LOADINGS[base] != loading:
                    break
                name = base
        else:
            combines[number] = {**row, "name": name}
    combine_of = {old: new for new, old in enumerate((int(n) for n in combines), 1)}
    combine_rows = {}
    for number, row in combines.items():
        new = combine_of[int(number)]
        terms = {f"C{define_of[int(key[1:])]}": value for key, value in row.items() if key.startswith("C")}
        combine_rows[str(new)] = {key: value for key, value in {**row, "row": new}.items() if not key.startswith("C")} | terms
    pickups = {}
    for number, row in document["pickup"].items():
        members = [combine_of[value] for key, value in row.items() if key.startswith("C") and value in combine_of]
        pickups[number] = {key: value for key, value in row.items() if not key.startswith("C")} | {
            f"C{index}": member for index, member in enumerate(members, 1)}
    return {**document,
            "load": {str(load_of[int(n)]): case for n, case in loads.items()},
            "define": {str(define_of[int(n)]): {"row": define_of[int(n)], **{
                f"C{index}": (1 if case > 0 else -1) * load_of[abs(case)] for index, case in enumerate(cases, 1)}}
                for n, cases in defines.items()},
            "combine": combine_rows, "pickup": pickups}
