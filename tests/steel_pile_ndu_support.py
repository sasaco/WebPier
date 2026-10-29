"""The NDU model of Example橋脚4 (a 鋼管ソイルセメント杭, decision 122) on the .sdc SOIL-JR 5.2 returned for it, for the tests of
the NDU and of the Aggre-SE project. The conditions of JRSNAP are these tests' (the example's are in its input once it has them)."""

from functools import cache
from pathlib import Path

from example4_support import EXAMPLE4_INPUT
from webpier.calc.column_rebar import column_layout
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.core.integrity import load_json
from webpier.export.jrsnap import LONGITUDINAL
from webpier.export.jrsnap.build_pile import build_pile_ndu
from webpier.export.soiljr import parse_sdc
from webpier.export.soiljr.sdc_seismic import parse_seismic
from webpier.inputs import parse_input

SDC = (Path(__file__).parent / "fixtures" / "soiljr" / "pile_steel_grid.sdc").read_bytes()
SPRINGS = parse_seismic(SDC)
CONDITIONS = {"shear_factor_vcd": 1.3, "shear_factor_vsd": 1.1, "shear_factor_vdd": 1.2, "analysis_steps": 600,
              "limited_final_step": 500, "target_displacement_m": 0.6}


@cache
def chain():
    data = load_json(EXAMPLE4_INPUT.read_bytes())
    for key in ("jrsnap_longitudinal", "jrsnap_transverse"):
        data[key].update(CONDITIONS)
    pier = parse_input(data)
    foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc(SDC))
    reaction = calculate_reaction(pier)
    return (pier, column_layout(pier), calculate_seismic_longitudinal(pier, foundation, reaction),
            calculate_seismic_transverse(pier, foundation, reaction))


def model(profile=LONGITUDINAL, reverse=False, springs=SPRINGS):
    pier, layout, longitudinal, transverse = chain()
    return build_pile_ndu(profile, pier, layout, longitudinal if profile is LONGITUDINAL else transverse, springs,
                          reverse=reverse)


