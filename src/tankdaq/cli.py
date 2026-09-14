from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .config import load,validate,ConfigError

def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog="tankdaq",description="Agitated-tank acquisition-only software; simulator or NI-DAQmx")
    p.add_argument("--version",action="version",version=__version__)
    sub=p.add_subparsers(dest="command",required=True)
    for name in ("validate","run"):
        s=sub.add_parser(name)
        s.add_argument("--config",type=Path,required=True)
        s.add_argument("--backend",choices=("sim","ni"),default="sim")
        s.add_argument("--raw-only",action="store_true",help="Save voltage/count data without unverified transmitter/flow scales")
        s.add_argument("--acknowledge-wiring",action="store_true",help="Affirm that physical wiring and voltage levels have been checked")
        if name=="run":
            s.add_argument("--duration",type=float,default=None,help="Duration in seconds; omit for continuous acquisition")
            s.add_argument("--output",type=Path,default=Path("runs"))
            s.add_argument("--quiet",action="store_true")
    s=sub.add_parser("devices",help="Enumerate NI devices, physical channels and terminal routes")
    s.add_argument("--output",type=Path)
    for name in ("inspect","watch","export","note","attach-rpm"):
        s=sub.add_parser(name)
        s.add_argument("run_folder",type=Path)
        if name=="watch":
            s.add_argument("--interval",type=float,default=2.)
            s.add_argument("--once",action="store_true")
        elif name=="export":
            s.add_argument("--format",choices=("csv","parquet"),default="csv")
            s.add_argument("--output",type=Path)
        elif name=="note": s.add_argument("message")
        elif name=="attach-rpm":
            s.add_argument("--csv",type=Path,required=True)
            s.add_argument("--alignment-note",required=True)
    return p

def main(argv: list[str] | None=None) -> int:
    args=parser().parse_args(argv)
    try:
        if args.command in {"validate","run"}:
            cfg=load(args.config)
            validate(cfg,backend=args.backend,raw_only=args.raw_only,acknowledge_wiring=args.acknowledge_wiring)
            if args.command=="validate":
                print("Configuration valid for requested mode. No hardware was accessed.")
                for ch in cfg["analog"]["channels"]:
                    if not ch["scale"]["confirmed"]:
                        print("Unconfirmed engineering scale:",ch["name"])
                if not cfg["counter"]["calibration_confirmed"]:
                    print("Unconfirmed flow calibration: q_water_l_min")
                return 0
            from .runner import run
            _,status=run(cfg,args.config,args.output,backend=args.backend,duration_s=args.duration,
                         raw_only=args.raw_only,acknowledge_wiring=args.acknowledge_wiring,quiet=args.quiet)
            return 1 if status=="failed" else (130 if status=="interrupted" else 0)
        if args.command=="devices":
            from .ni_backend import inventory
            result=inventory()
            text=json.dumps(result,indent=2,default=str)
            print(text)
            if args.output: args.output.write_text(text+"\n",encoding="utf-8")
            return 0
        from . import data_tools as d
        if args.command=="inspect": print(json.dumps(d.inspect_run(args.run_folder),indent=2))
        elif args.command=="watch": d.watch(args.run_folder,args.interval,args.once)
        elif args.command=="export": print(d.export_run(args.run_folder,args.format,args.output))
        elif args.command=="note": d.add_note(args.run_folder,args.message);print("Operator event recorded.")
        elif args.command=="attach-rpm": print(d.attach_rpm(args.run_folder,args.csv,args.alignment_note))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2
