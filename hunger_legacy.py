from hungerDataStructs import *

from datetime import datetime as dt
import os
from statistics import pstdev
from numpy import percentile as pct

class Solver:
    def __init__(self, metricID, numDist):
        Logger.initialize()
        self.reset(metricID, numDist)

    def __del__(self):
        Logger.cleanup()

    # External Getters ----------------------------------------------------------------------------

    def reset(self, metricID, numDist):
        self.inProgress = False
        if isinstance(metricID, str):
            self.metricID = metricID
        elif isinstance(metricID, int):
            self.metricID = allowed[metricID]
        self.placements = {region: 0 for region in sorted(regionlist.values(), key=lambda region: region.code)}
        self.placedRegions = []
        self.failures = set()
        self.districts = [District(i+1) for i in range(numDist)]

        # Time logging
        self.startTime = 0
        self.lastTime = 0
        self.times = {}
        self.occurred = self.times.copy()

        # Calculate the minimum acceptable standard deviation
        maxRegionMetric = self.__getLargestUnplacedFor().metrics[self.metricID]
        allOtherMetrics = sum(region.metrics[self.metricID] for region in self.__getUnplacedRegions()) - maxRegionMetric
        if numDist <= 1 or allOtherMetrics/(numDist-1) > maxRegionMetric:
            self.minAcceptable = 0.5
        else:
            hypothetical = [maxRegionMetric] + [allOtherMetrics/(numDist-1)]*(numDist-1)
            percentile = 100*pstdev(hypothetical)/sum(hypothetical)
            self.minAcceptable = max(0.5, percentile)

    def isSolved(self):
        return all(placement != 0 for placement in self.placements.values()) and self.getStandardDevAsPercent() < self.minAcceptable

    def getStandardDevAsPercent(self):
        metrics = [district.metric for district in self.districts]
        return 100*pstdev(metrics)/sum(metrics)

    def getTimeSinceStarted(self):
        if self.startTime == 0:
            return -1
        else:
            return (self.lastTime - self.startTime).total_seconds()

    def getEmptyDataFrame():
        return {new_list: [] for new_list in ["region","code","district","metric"]}

    def getDummyDataFrame():
        result = Solver.getEmptyDataFrame()

        result["region"].append("none")
        result["code"].append("none")
        result["district"].append(str(1))
        result["metric"].append("none")

        return result

    def getCurrentDataFrame(self):
        result = Solver.getEmptyDataFrame()

        for district in self.districts:
            for region in district.regions:
                result["region"].append(region.name)
                result["code"].append(region.code)
                result["district"].append(str(district.index))
                result["metric"].append(region.metrics[self.metricID])

        if len(result["region"]) == 0:
            result = Solver.getDummyDataFrame()

        return result

    def getStarters(self):
        self.__seedStarters(True)
        return self

    # Printers ------------------------------------------------------------------------------------

    def printResult(self):
        Logger.l("\n\n+---------------------------------------------------------+")

        for district in self.districts:
            print("District {} ({}):".format(district.index, district.metric))
            print("|".join(sorted(region.code for region in district.regions)))
            print()

        return self

    def printConcise(self):
        placedRegions = sorted(self.placedRegions, key=lambda region: region.code)
        formatstr = "|".join(["{:^" + str(len(placedRegions[0].code)) + "}"]*len(placedRegions))
        print(formatstr.format(*(region.code for region in placedRegions)))
        print(formatstr.format(*(self.placements[region] for region in placedRegions)))

        return self

    def printSummary(self):
        print("\t{:>10}({}) took {:.3f}s ({:.3f}%, {} failures)".format(self.metricID,
                                                                    len(self.districts),
                                                                    self.getTimeSinceStarted(),
                                                                    self.getStandardDevAsPercent(),
                                                                    len(self.failures)))

        return self

    def __doStepLogging(self):
        total = sum(self.times.values())
        total = 1 if total == 0 else total
        #timesToPrint = { key: time for key, time in sorted(self.times.items()) if key in [] }
        timesToPrint = { key: time for key, time in sorted(self.times.items()) }
        result = []

        # Failure count
        result.append("failures")
        result.append("")
        result.append(len(self.failures))

        # Time so far
        result.append("total")
        result.append("")
        result.append(self.getTimeSinceStarted())

        # Times
        for key, time in timesToPrint.items():
            result.append(key)
            result.append(self.occurred[key])

            percent = 100*time/total
            if percent > 70:
                result.append(color.RED)
            elif percent > 20:
                result.append(color.YELLOW)
            else:
                result.append(color.GREEN)
            result.append(percent)

        # Put it all together
        formatStr = " | ".join(["{}: {}{:<6}" + Style.RESET_ALL] + ["{}: {}{:7.3f}" + Style.RESET_ALL] + ["{}({:4}):{}{:6.2f}%" + Style.RESET_ALL]*len(timesToPrint))
        resultStr = formatStr.format(*result)
        # Subtract out the hidden style characters
        numChars = len(resultStr) - 9 * len(timesToPrint)

        # Progress bar
        # The number of available cells for progress bar
        availCells = os.get_terminal_size().columns - numChars - 14
        # The number we'll actually use - closest 10, rounding down (no rounding if less than 10)
        numCells = availCells if availCells <= 10 else availCells - (availCells%10)

        if numCells > 5:
            percent = 100*len(self.placedRegions)/len(self.placements)
            if percent < 50:
                progressColor = color.RED
            elif percent < 90:
                progressColor = color.YELLOW
            else:
                progressColor = color.GREEN
            progressbar = ("completion: {}+{:" + "{}".format(numCells) + "}+" + Style.RESET_ALL + " | ").format(progressColor, "="*round(percent*(numCells/100)))
            suffix = ""
        else:
            progressbar = ""
            suffix = (os.get_terminal_size().columns - numChars)*" "

        # Put it all together!
        print(progressbar + resultStr + suffix, end="\r")

    # Setters -------------------------------------------------------------------------------------

    def __addToFailures(self):
        self.failures.add(frozenset(self.placements.items()))

    def __place(self, region, district):
        district.addRegion(region, self.metricID)
        self.placedRegions.append(region)
        self.placements[region.code] = district.index

    def __popLastPlaced(self, district):
        for region in reversed(self.placedRegions):
            # ignore regions that are already in this district
            if region in district.regions:
                continue

            district = self.districts[self.placements[region]-1]
            district.removeRegion(region, self.metricID)
            self.placedRegions.remove(region)
            self.placements[region.code] = 0

            return region

        return False

    def __updateTime(self, tag = None):
        if self.startTime == 0:
            self.startTime = dt.now()

        if not tag:
            self.lastTime = dt.now()
        else:
            newTime = dt.now()
            self.times[tag] = self.times.get(tag, 0) + (newTime - self.lastTime).total_seconds()
            self.occurred[tag] = self.occurred.get(tag, 0) + 1
            self.lastTime = newTime

    def __addUnusedDistricts(self):
        unusedDistricts = self.__getUnusedDistricts()
        for ud in unusedDistricts:
            adjacentSet = set(ud.adj)
            for d in self.districts:
                # If this unused district's adjacent regions are all in district d, AND there are some adjacent regions (sorry Alaska), add them all!
                if adjacentSet and adjacentSet <= d.regions:
                    if not self.__canAddToDistrict(ud.regions, d):
                        return False
                    Logger.s("!", d.index, "enclosed regions:", ud.regions)
                    for region in ud.regions:
                        self.__place(region, d)

        return True

    def __seedStarters(self, doStatus = False):
        distances = distanceMatrix.copy()
        percentile = pct([region.metrics[self.metricID] for region in regionlist.values()], 50)
        for district in self.districts:
            minDistances = {}
            for code in (region.code for region in self.__getUnplacedRegions() if region.metrics[self.metricID] > percentile):
                reachablePlacedRegions = { region.code: distances[code][region.code] for region in self.placedRegions if distances[code][region.code] > 0 }
                if len(reachablePlacedRegions) > 0:
                    minDistances[code] = min(reachablePlacedRegions.items(), key=lambda item: item[1])

            if len(minDistances) == 0:
                region = self.__getLargestUnusedRegionFor(lambda region: True)
            else:
                code = max(minDistances, key=lambda code: minDistances[code][1])
                region = regionlist[code]

            self.__place(region, district)

    # Internal getters ----------------------------------------------------------------------------

    def __canAddToDistrict(self, regions, district):
        if isinstance(regions, Region):
            regions = [regions]
        currState = self.placements.copy()
        for region in regions:
            currState[region.code] = district.index
        return frozenset(currState.items()) not in self.failures

    def __getLargestUnplacedFor(self, district=None):
        if district==None:
            unplaced = (region for region in self.__getUnplacedRegions())
            sorter = lambda region: region.metrics[self.metricID]
        else:
            unplaced = (region for region in self.__getUnplacedRegions() if (region.code in district.adj or len(region.adj) == 0) and self.__canAddToDistrict(region, district))
            sorter = lambda region: (district.adj.get(region.code,0), region.metrics[self.metricID])

        return max(unplaced, key=sorter, default=False)

    def __getNextStarter(self):
        # Get the distances
        minDistances = {}
        percentile = pct([region.metrics[self.metricID] for region in self.__getUnplacedRegions()], 50)
        for region in filter(lambda region: region.metrics[self.metricID] >= percentile, self.__getUnplacedRegions()):
            reachablePlacedRegions = { inRegion: distanceMatrix[region][inRegion] for inRegion in self.placedRegions if distanceMatrix[region][inRegion] > 0 }
            minDistances[region] = min(reachablePlacedRegions.items(), key=lambda item: item[1], default=("", float("inf")))

        # If nothing is reachable, just get the biggest unused region
        if all(distance[1] == float("inf") for distance in minDistances.values()):
            return self.__getLargestUnplacedFor()

        # If we can reach some items, get those items!
        else:
            return max(minDistances, key=lambda code: minDistances[code][1], default=False)

    def __getUnusedRegionFor(self, criteria):
        return next((region for region in self.__getUnusedRegionsFor(criteria)), False)

    def __getLargestUnusedRegionFor(self, criteria):
        return max(self.__getUnusedRegionsFor(criteria),
                   key=lambda region: region.metrics[self.metricID],
                   default=False)

    def __getLargestUnusedRegionForDistrict(self, district, criteria):
        return max(self.__getUnusedRegionsFor(lambda region: region.code in district.adj and criteria(region)),
                   key=lambda region: (district.adj[region.code], region.metrics[self.metricID]),
                   default=False)

    def __getLargestUnusedNeighborlessRegionFor(self, criteria):
        disconnectedRegions = [region for district in self.__getUnusedDistricts() if len(district.adj) == 0 for region in district.regions]
        return max(self.__getUnusedRegionsFor(lambda region: region in disconnectedRegions and criteria(region)),
                   key=lambda region: region.metrics[self.metricID],
                   default=False)

    def __getUnusedRegionsFor(self, criteria):
        # filter to get the regions matching this criteria
        return filter(criteria, self.__getUnplacedRegions())

    def __getUnusedDistricts(self):
        # Group unused regions into districts
        regionsToBePlaced = sorted(self.__getUnplacedRegions(), key=lambda region: len(region.adj))
        while seedRegion := next(iter(regionsToBePlaced), False):
            unusedDistrict = District(0)
            unusedDistrict.addRegion(seedRegion, self.metricID)
            regionsToBePlaced.remove(seedRegion)

            while adjRegion := next(filter(lambda region: region.code in unusedDistrict.adj, regionsToBePlaced), False):
                unusedDistrict.addRegion(adjRegion, self.metricID)
                regionsToBePlaced.remove(adjRegion)

            yield unusedDistrict

    def __getUnplacedRegions(self):
        for region in filter(lambda region: self.placements[region] == 0, self.placements):
            yield region

    # Solve it ------------------------------------------------------------------------------------

    def doStep(self, doStatus = False):
        self.__updateTime()
        # Don't double-dip, and don't perform this if it's solved
        if self.inProgress or self.isSolved():
            return

        self.__updateTime("checkSolved")

        self.inProgress = True

        # get the smallest district
        district = min(self.districts)

        self.__updateTime("getMinDistrict")

        if all(len(district.regions) == 0 for district in self.districts):
            self.__seedStarters(doStatus)
            self.__updateTime("seed")
        # if this district has no neighbors (either empty or only containing neighborless regions), append the largest unused Region
        elif len(district.adj) == 0 and (region := self.__getLargestUnusedRegionFor(lambda region: self.__canAddToDistrict(region, district))):
            self.__updateTime("selectMax")
            self.__place(region, district)
        # else if there are adjacent regions, add the biggest one
        elif region := self.__getLargestUnusedRegionForDistrict(district, lambda region: self.__canAddToDistrict(region, district)):
            self.__updateTime("selectAdj")
            self.__place(region, district)
        # else if there are neighborless regions, add the biggest one
        elif region := self.__getLargestUnusedNeighborlessRegionFor(lambda region: self.__canAddToDistrict(region, district)):
            self.__updateTime("selectNoNb")
            self.__place(region, district)
        # else step backwards until we find something we can add to this district
        else:
            self.__updateTime("selectFailed")
            # Whatever led us to this point failed us - record the failure
            self.__addToFailures()

            while region := self.__popLastPlaced(district):
                if region in district.adj and self.__canAddToDistrict(region, district):
                    self.__updateTime("backtrack")
                    self.__place(region, district)
                    break
                else:
                    self.__addToFailures()

        self.__updateTime("add region")

        if all(len(district.regions) > 0 for district in self.districts) and not self.isSolved():
            if not self.__addUnusedDistricts():
                # Whatever led us to this point failed us - record the failure
                self.__addToFailures()
            self.__updateTime("checkUnused")

        self.inProgress = False

        # Do the logging for this step
        if doStatus:    self.__doStepLogging()

    def solve(self, doStatus = False, doLogging = False):
        Logger.doLogging = doLogging
        # Don't show the progress bar if logging is enabled
        if doLogging:   doStatus = False

        while not self.isSolved():
            self.doStep(doStatus)

        if doStatus:    print()

        return self

# Solve and unit test

import cProfile
import pstats

def profile(string):
    filename = "stats.profile"
    cProfile.run(string, filename)
    stats = pstats.Stats(filename)
    stats.strip_dirs()
    stats.sort_stats("tottime")
    stats.print_stats(10)

def unitTest(count, doStatus=True):
    solver = Solver(0, 1)
    result = {new_list: [] for new_list in allowed}
    for count in range(1, count + 1):
        if doStatus: print("{} districts".format(count))
        for metric in allowed:
            tick = dt.now()
            solver.reset(metric, count)
            solver.solve(doStatus).printSummary()
            result[metric].append((dt.now() - tick).total_seconds())

    # Write to file
    i = 0
    while os.path.exists("logs/log{}.txt".format(i)):
        i += 1

    metricFmt = "{:>13} |"
    intFmt = " | ".join(["{:^9}"]*count)+"\n"
    floatFmt = " | ".join(["{:^9.3f}"]*count)+"\n"
    with open("logs/log{}.txt".format(i), "w", encoding='utf8') as log:
        log.write((metricFmt.format("") + intFmt.format(*range(1,count + 1))))
        for metric, values in result.items():
            log.write((metricFmt.format(metric) + floatFmt.format(*values)))

def lightUnitTest(start=1, end=6):
    for count in range(start, end+1):
        for metric in allowed:
            Solver(metric, count).solve(True).printSummary()

#lightUnitTest()
#unitTest(6)
#profile("Solver(4, 3).solve().printConcise()")
#Solver(1, 4).solve(doLogging=True).printResult().printConcise()
#Solver(0, 10).getStarters().printConcise()