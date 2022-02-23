import time
import socket
import subprocess
import numpy as np
import amaranth as am
import matplotlib.pyplot as plt
from collections import namedtuple
from amaranth.vendor.lattice_ecp5 import LatticeECP5Platform
from amaranth.build import Resource, Pins, Attrs, Clock


PLLSettings = namedtuple(
    "PLLSettings",
    [
        "clki_div",  # 1-128
        "clkop_div",  # 1-128
        "clkfb_div",  # 1-80
        "kvco",  # 0-7
        "lpf_capacitor",  # 0-3
        "lpf_resistor",  # 0-127
        "icp_current",  # 0-31
        "mfg_gmc_gain",  # 0-7
        "mfg_gmc_test",  # 0-15
        "mfg_force_vfilter",  # 0-1
        "mfg_icp_test",  # 0-1
        "mfg_gmcref_sel",  # 0-3
        "mfg_en_filteropamp",  # 0-1
    ],
)


SASettings = namedtuple(
    "SASettings",
    [
        "freq_center",      # Hz
        "freq_span",        # Hz
        "ampl_att",         # dB
        "bw_rbw",           # Hz
        "bw_vbw",           # Hz
    ],
)


class PLLSettings(PLLSettings):
    @classmethod
    def default(cls):
        return cls(
            clki_div=1,
            clkop_div=3,
            clkfb_div=10,
            kvco=0,
            lpf_capacitor=0,
            lpf_resistor=8,
            icp_current=12,
            mfg_gmc_gain=0,
            mfg_gmc_test=14,
            mfg_force_vfilter=0,
            mfg_icp_test=0,
            mfg_gmcref_sel=2,
            mfg_en_filteropamp=1,
        )

    def valid(self):
        return (
            self.clki_div in range(1, 128 + 1)
            and self.clkop_div in range(1, 128 + 1)
            and self.clkfb_div in range(1, 80 + 1)
            and self.kvco in range(0, 7 + 1)
            and self.lpf_capacitor in (0, 1, 2, 3)
            and self.lpf_resistor in range(0, 127 + 1)
            and self.icp_current in range(0, 31 + 1)
            and self.mfg_gmc_gain in range(0, 7 + 1)
            and self.mfg_gmc_test in range(0, 15 + 1)
            and self.mfg_force_vfilter in (0, 1)
            and self.mfg_icp_test in (0, 1)
            and self.mfg_gmcref_sel in (0, 1, 2, 3)
            and self.mfg_en_filteropamp in (0, 1)
        )

    def freq_out(self):
        return (20e6 / self.clki_div) * self.clkfb_div

    def freq_vco(self):
        return self.freq_out() * self.clkop_div


class SASettings(SASettings):
    @classmethod
    def default(cls):
        return cls(
            freq_center=200e6,
            freq_span=5e6,
            ampl_att=30,
            bw_rbw=1000,
            bw_vbw=1000,
        )

    def valid(self):
        bws = (10, 30, 100, 300, 1e3, 3e3, 10e3, 30e3, 100e3, 300e3, 1e6)
        return (
            0 <= self.freq_center <= 3.2e9
            and 0 <= self.freq_span <= 3.2e9
            and 0 <= self.ampl_att <= 50
            and self.bw_rbw in bws
            and self.bw_vbw in bws
        )


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
    def __init__(self, pll_settings):
        if not pll_settings.valid():
            raise ValueError("Invalid PLL settings")
        self.pll_settings = pll_settings

    def elaborate(self, platform):
        m = am.Module()
        clk20 = platform.request("clk20")
        aux = platform.request("aux")
        cd_sync = am.ClockDomain(reset_less=True)
        m.domains += cd_sync
        m.d.comb += aux.o.eq(cd_sync.clk)
        pll = self.pll_settings
        m.submodules.pll = am.Instance(
            "EHXPLLL",
            a_FREQUENCY_PIN_CLKI="20",
            a_FREQUENCY_PIN_CLKOP=str(pll.freq_out() // 1e6),
            a_KVCO=str(pll.kvco),
            a_LPF_CAPACITOR=str(pll.lpf_capacitor),
            a_LPF_RESISTOR=str(pll.lpf_resistor),
            a_ICP_CURRENT=str(pll.icp_current),
            a_MFG_GMC_GAIN=str(pll.mfg_gmc_gain),
            a_MFG_GMC_TEST=str(pll.mfg_gmc_test),
            a_MFG_FORCE_VFILTER=str(pll.mfg_force_vfilter),
            a_MFG_ICP_TEST=str(pll.mfg_icp_test),
            a_MFG_GMCREF_SEL=str(pll.mfg_gmcref_sel),
            a_MFG_ENABLE_FILTEROPAMP=str(pll.mfg_en_filteropamp),
            p_CLKI_DIV=pll.clki_div,
            p_CLKFB_DIV=pll.clkfb_div,
            p_CLKOP_DIV=pll.clkop_div,
            p_CLKOP_ENABLE="ENABLED",
            p_CLKOP_CPHASE=7,
            p_CLKOP_FPHASE=0,
            p_FEEDBK_PATH="CLKOP",
            i_CLKI=clk20.i,
            o_CLKOP=cd_sync.clk,
            i_CLKFB=cd_sync.clk,
        )
        return m


def load_bitstream(pll_settings):
    plat = Platform()
    top = Top(pll_settings)
    plat.build(top, "ecppll", "build/", ecppack_opts=["--compress"])
    subprocess.run(["ecpdap", "program", "-q", "-f", "30000", "build/ecppll.bit"])


class SSA3021X:
    def __init__(self, ip_address, sa_settings):
        if not sa_settings.valid():
            raise ValueError("Invalid SA settings")
        self.sa_settings = sa_settings
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((ip_address, 5025))
        self.configure()

    def configure(self):
        sa = self.sa_settings
        self.sock.settimeout(1)
        self.command(":SYSTEM:PRESET:TYPE DEFAULT")
        self.command(":INIT:CONTINUOUS OFF")
        self.command(f":SENSE:FREQ:CENTER {sa.freq_center}")
        self.command(f":SENSE:FREQ:SPAN {sa.freq_span}")
        self.command(":DISP:WINDOW:TRACE:Y:SCALE:RLEVEL 10 DBM")
        self.command(":SENSE:POWER:RF:ATT:AUTO OFF")
        self.command(f":SENSE:POWER:RF:ATT {sa.ampl_att}")
        self.command(":SENSE:SWEEP:TIME:AUTO ON")
        self.command(":SENSE:SWEEP:COUNT 1")
        self.command(":SENSE:BWIDTH:RES:AUTO OFF")
        self.command(":SENSE:BWIDTH:VIDEO:AUTO OFF")
        self.command(f":SENSE:BWIDTH:RES {sa.bw_rbw}")
        self.command(f":SENSE:BWIDTH:VIDEO {sa.bw_vbw}")

    def measure(self):
        sweep_time = max(5, float(self.query(":SENSE:SWEEP:TIME?")))
        self.sock.settimeout(sweep_time * 1.2)
        self.command(":INIT:IMMEDIATE")
        self.sock.settimeout(1)
        resp = self.query(":TRACE:DATA? 1")
        return [float(s) for s in resp.split(",")[:-1]]

    def command(self, cmd):
        self.sock.send(cmd.encode() + b"\n*OPC?\n")
        resp = self.sock.recv(8)
        if resp != b"1\n":
            raise RuntimeError(f"Unexpected response from SSA3021X: {resp}")

    def query(self, cmd):
        self.sock.send(cmd.encode() + b"\n")
        buf = self.sock.recv(8192)
        while buf[-1] != ord('\n'):
            buf += self.sock.recv(8192)
        return buf.decode()


if __name__ == "__main__":
    pll_settings = PLLSettings.default()
    sa_settings = SASettings(
        freq_center=pll_settings.freq_out(),
        freq_span=5e6,
        ampl_att=30,
        bw_rbw=300,
        bw_vbw=300,
    )

    sa = SSA3021X("ssa", sa_settings)
    sa.configure()

    fc = sa_settings.freq_center
    fs = sa_settings.freq_span
    freqs = np.linspace(fc - fs/2, fc + fs/2, 751)

    currents = range(0, 12)
    for i in currents:
        print(f"Trying ICP_CURRENT={i}")
        load_bitstream(pll_settings._replace(icp_current=i))
        time.sleep(0.1)
        trace = sa.measure()
        plt.plot(freqs, trace, label=f"ICP_CURRENT={i}")

    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Power (dBm)")
    plt.legend()
    plt.show()
