import hunger as h
import hunger_old as ho
import hunger_gui as hg
from multiprocessing import Pool
import cProfile
import pstats

# Utilities ---------------------------------------------------------------------------------------

def getStringFor(in1, in2, title, syntax):
    rst = h.Style.RESET_ALL
    if in1 > in2:
        color1 = h.color.RED
        color2 = h.color.GREEN
        comp = ">"
    elif in1 < in2:
        color1 = h.color.GREEN
        color2 = h.color.RED
        comp = "<"
    else:
        color1 = h.color.YELLOW
        color2 = h.color.YELLOW
        comp = "="

    fmt = "{:>10}{}{:>" + syntax + "}" + rst + " " + comp + " {}{:<" + syntax + "}" + rst
    return fmt.format(title, color1, in1, color2, in2)

def printDiffs(hs, hos):
    hPlaced = set(hs.placements.items())
    hoPlaced = set(hos.placements.items())
    diff = { region.code for region, placement in (hPlaced - hoPlaced) } | { region.code for region, placement in (hoPlaced - hPlaced) }

    print("{:>10}{:>8} | {:<8}".format("", "curr", "old"))
    print(getStringFor(hs.getTimeSinceStarted(), hos.getTimeSinceStarted(), "time", "8.3f"))
    print(getStringFor(hs.getStandardDevAsPercent(), hos.getStandardDevAsPercent(), "stddev", "8.3f"))
    print(getStringFor(len(hs.failures), len(hos.failures), "fails", "8"))

    if len(diff) == 0:
        print("No differences!")
        return False
    
    print(diff)
    print(hs.placements)

    placedRegions = sorted(diff)
    formatstr = "|".join(["{:^" + str(len(placedRegions[0])) + "}"]*len(placedRegions))
    print(formatstr.format(*placedRegions))
    print(formatstr.format(*(hs.placements[region] for region in placedRegions)))
    print(formatstr.format(*(hos.placements[region] for region in placedRegions)))

    return True

def showFor(hs, hos=None):
    if hos:
        hg.getMapFor(hs.getCurrentDataFrame(), "hunger: {} ({})".format(hs.metricID, len(hs.districts))).show()
        hg.getMapFor(hos.getCurrentDataFrame(), "hunger_old: {} ({})".format(hos.metricID, len(hos.districts))).show()
    else:
        hg.getMapFor(hs.getCurrentDataFrame(), "both: {} ({})".format(hs.metricID, len(hs.districts))).show()

def profile(string):
    filename = "stats.profile"
    cProfile.run(string, filename)
    stats = pstats.Stats(filename)
    stats.strip_dirs()
    stats.sort_stats("cumtime")
    stats.print_stats(10)
    print()
    stats.sort_stats("tottime")
    stats.print_stats(10)

def solveParallel(metric, count):
    with Pool() as pool:
        return pool.apply(h.Solver.solve, args=(h.Solver(metric, count), False, False)), pool.apply(ho.Solver.solve, args=(ho.Solver(metric, count), False, False))

# Solvers -----------------------------------------------------------------------------------------

def stepThrough(metric, count):
    hs = h.Solver(metric, count)
    hos = ho.Solver(metric, count)

    h.Logger.doLogging = True
    while not hs.isSolved() or not hos.isSolved():
        hs.doStep()
        hos.doStep()
        if (input("Enter \"y\" to print, or enter to continue: ") == "y"):
            showFor(hs, hos)
            
    showFor(hs, hos)

def onCondition(metric, count):
    hs = h.Solver(metric, count)

    lastPlaced = 0
    while not hs.isSolved():
        hs.doStep()
        curPlaced = len(hs.placedRegions)
        if lastPlaced >= curPlaced:
            showFor(hs)
            h.Logger.doLogging=True
        lastPlaced = curPlaced

    hs.printSummary()

    showFor(hs)

def timeTrial(start=1, end=6):
    times = [0,0]
    stddevs = [0,0]
    fails = [0,0]
    for count in range(start, end+1):
        for metric in h.allowed:
            print(" --------------- {} {} --------------- ".format(count, metric))
            hs, hos = solveParallel(metric, count)

            times[0] += hs.getTimeSinceStarted()
            times[1] += hos.getTimeSinceStarted()
            stddevs[0] += hs.getStandardDevAsPercent()
            stddevs[1] += hos.getStandardDevAsPercent()
            fails[0] += len(hs.failures)
            fails[1] += len(hos.failures)

            printDiffs(hs, hos)
            print()
        print()

    print("Cumulative")
    print(getStringFor(*times, "time", "8.3f"))
    print(getStringFor(*stddevs, "stddev", "8.3f"))
    print(getStringFor(*fails, "fails", "8"))

def unitTest(start=1, end=6, doStatus=True, doLogging=False):
    tests = map(h.Solver.solve,
                ( h.Solver(metric, count) for metric in h.allowed for count in range(start, end+1) ), 
                [ doStatus ] * len(h.allowed) * (end + 1 - start), 
                [ doLogging ] * len(h.allowed) * (end + 1 - start))
    for solver in tests:
        solver.printSummary()

def threadUnitTest(start=1, end=6):
    pool = Pool()
    threadqueue = pool.map(h.Solver.solve, ( h.Solver(metric, count) for metric in h.allowed for count in range(start, end+1) ))
    pool.close()
    pool.join()

    for solver in threadqueue:
        solver.printSummary()
    
    return threadqueue

def threadUnitTestLogging(start=1, end=6):
    threadqueue = threadUnitTest(start, end)
    
    result = { metric: [] for metric in h.allowed }
    for solver in threadqueue:
        result[solver.metric].append(solver.getTimeSinceStarted())
    
    # Write to file
    i = 0
    datestr = date.today().strftime("%Y-%m-%d")
    filename = "logs/{} log{}.txt".format(datestr, i)
    while os.path.exists(filename):
        i += 1
        filename = "logs/{} log{}.txt".format(datestr, i)

    metricFmt = "{:>13} |"
    intFmt = " | ".join(["{:^9}"]*count)+"\n"
    floatFmt = " | ".join(["{:^9.3f}"]*count)+"\n"
    with open(filename, "w", encoding='utf8') as log:
        log.write((metricFmt.format("") + intFmt.format(*range(1,count + 1))))
        for metric, values in result.items():
            log.write((metricFmt.format(metric) + floatFmt.format(*values)))

if __name__ == '__main__':
    h.init()
    #profile("h.Solver(0,2).solve().printSummary()")
    #profile("UnitTest(doStatus=False)")
    
    #unitTest(doStatus=False)
    #threadUnitTest(end=4)
    
    timeTrial(start=2, end=4)
    #h.Solver(0,4).solve.printSummary()
    #showFor(h.Solver(0, 4).solve().printSummary(), ho.Solver(0, 4).solve().printSummary())
    #h.Solver(0, 1).solve(doLogging=True)

    #showFor(h.Solver(0, 5).solve().printSummary())
    h.deinit()