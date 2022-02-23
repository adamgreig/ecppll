import subprocess
import amaranth as am
from amaranth.vendor.lattice_ecp5 import LatticeECP5Platform
from amaranth.build import Resource, Pins, Attrs, Clock


class Platform(LatticeECP5Platform):
    device = "LFE5UM-85F"
    package = "BG381"
    speed = "7"
    connectors = []
    resources = [
        Resource(
            "clk20",
            0,
            Pins("P3", dir="i"),
            Attrs(IO_TYPE="LVCMOS33"),
            Clock(20e6),
        ),
        Resource(
            "aux",
            0,
            Pins("A12", dir="o"),
            Attrs(IO_TYPE="LVCMOS33", DRIVE="4"),
        ),
    ]


class Top(am.Elaboratable):
    def __init__(
        self,
        clki_div=1,                 # 1-128
        clkop_div=3,                # 1-128
        clkfb_div=10,               # 1-80
        kvco="0",                   # 0-7
        lpf_capacitor="0",          # 0-3
        lpf_resistor="8",           # 0-127
        icp_current="12",           # 0-31
        mfg_gmc_gain="0",           # 0-7
        mfg_gmcref_sel="2",         # 0-3
        mfg_en_filteropamp="1",     # 0-1
    ):
        self.clki_div = clki_div
        self.clkop_div = clkop_div
        self.clkfb_div = clkfb_div
        self.kvco = kvco
        self.lpf_capacitor = lpf_capacitor
        self.lpf_resistor = lpf_resistor
        self.icp_current = icp_current
        self.mfg_gmc_gain = mfg_gmc_gain
        self.mfg_gmcref_sel = mfg_gmcref_sel
        self.mfg_en_filteropamp = mfg_en_filteropamp
        self.fout = (20e6 / clki_div) * clkfb_div
        self.vco = self.fout * self.clkop_div

    def elaborate(self, platform):
        m = am.Module()
        clk20 = platform.request("clk20")
        aux = platform.request("aux")
        cd_sync = am.ClockDomain(reset_less=True)
        m.domains += cd_sync
        m.d.comb += aux.o.eq(cd_sync.clk)
        m.submodules.pll = am.Instance(
            "EHXPLLL",
            a_FREQUENCY_PIN_CLKI="20",
            a_FREQUENCY_PIN_CLKOP=str(self.fout//1e6),
            a_KVCO=str(self.kvco),
            a_LPF_CAPACITOR=str(self.lpf_capacitor),
            a_LPF_RESISTOR=str(self.lpf_resistor),
            a_ICP_CURRENT=str(self.icp_current),
            a_MFG_GMC_GAIN=str(self.mfg_gmc_gain),
            a_MFG_GMCREF_SEL=str(self.mfg_gmcref_sel),
            a_MFG_ENABLE_FILTEROPAMP=str(self.mfg_en_filteropamp),
            p_CLKI_DIV=self.clki_div,
            p_CLKFB_DIV=self.clkfb_div,
            p_CLKOP_ENABLE="ENABLED",
            p_CLKOP_CPHASE=7,
            p_CLKOP_FPHASE=0,
            p_FEEDBK_PATH="CLKOP",
            i_CLKI=clk20.i,
            o_CLKOP=cd_sync.clk,
            i_CLKFB=cd_sync.clk,
        )
        return m


def load_bitstream(**kwargs):
    plat = Platform()
    top = Top(**kwargs)
    plat.build(top, "ecppll", "build/", ecppack_opts=["--compress"])
    subprocess.run(["ecpdap", "program", "build/ecppll.bit"])


if __name__ == "__main__":
    load_bitstream()
