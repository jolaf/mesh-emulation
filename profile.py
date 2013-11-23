from pstats import Stats
Stats('Mesh.prof').sort_stats('tottime').print_stats(20)
