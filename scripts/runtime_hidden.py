"""Earliest frozen-app hook: prevent helper console windows before Qt imports."""
from kinetic_cut.process import install_desktop_process_policy
install_desktop_process_policy()
