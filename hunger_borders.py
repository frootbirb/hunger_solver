from hungerDataStructs import *

from datetime import datetime as dt
import os
from statistics import pstdev
from numpy import percentile as pct, sqrt

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

        regionsToBePlaced = sorted(self.__getUnplacedRegions(), key=lambda region: len(region.adj))
        self.unusedDistricts = list(self.__getUnusedDistrictsFor(regionsToBePlaced))

        self.failures = set()
        self.districts = [District(i+1) for i in range(numDist)]

        # Time logging
        self.startTime = 0
        self.lastTime = 0
        self.times = {}
        self.occurred = self.times.copy()
        Logger.logDepth = ""

        # Calculate the maximum district size

        '''
        m = mean
        s = sumAll
        n = numDist
        l = large value

        0.5 = 100*stddev/s
        s/200 = stddev                = sqrt(((l - m)**2     +  (n-1)*((s - l)/(n - 1) - m)**2)/n)
        s**2/40000                    =      ((l - m)**2     +  (n-1)*((s - l)/(n - 1) - m)**2)/n
        n*s**2/40000                  =       (l - m)**2     +  (n-1)*((s - l)/(n - 1) - m)**2
        n*s**2/40000                  = l**2 - 2*m*l + m**2  +  (n-1)*((s - l)**2/(n - 1)**2 -       2*m*(s - l)/(n - 1) +       m**2)
        n*s**2/40000                  = l**2 - 2*m*l + m**2  +   (n-1)*(s - l)**2/(n - 1)**2 - (n-1)*2*m*(s - l)/(n - 1) + (n-1)*m**2
        n*s**2/40000                  = l**2 - 2*m*l + m**2  +         (s - l)**2/(n - 1)    -       2*m*(s - l)         + (n-1)*m**2
        n*s**2/40000                  = l**2 - 2*m*l + m**2  +         (s - l)**2/(n - 1)    -     (2*m*s - 2*m*l)       + (n-1)*m**2
        n*s**2/40000                  = l**2 - 2*m*l + m**2  +         (s - l)**2/(n - 1)    -      2*m*s + 2*m*l        + (n-1)*m**2
        n*s**2/40000                  = l**2 - 2*m*l + 2*m*l +         (s - l)**2/(n - 1)    -      2*m*s                + (n-1)*m**2 + m**2
        n*s**2/40000                  = l**2 +               +         (s - l)**2/(n - 1)    -      2*m*s                +     n*m**2
        n*s**2/40000 + 2*m*s - n*m**2 = l**2 +                   (s**2 - 2*s*l + l**2)/(n - 1)
        n*s**2/40000 + 2*m*s - n*m**2 = l**2 +         s**2/(n - 1) - 2*s/(n - 1)*l + (1/(n - 1))*l**2
        n*s**2/40000 + 2*m*s - n*m**2 = (1 + 1/(n - 1))l**2 - 2*s/(n - 1)*l + s**2/(n - 1)
        0 = (1 + 1/(n - 1))l**2 - 2*s/(n - 1)*l + s**2/(n - 1) - (n*s**2/40000 + 2*m*s - n*m**2)
        0 = (1 + 1/(n - 1))l**2 - 2*s/(n - 1)*l + s**2/(n - 1) - n*s**2/40000 - 2*m*s + n*m**2
        '''

        sumAll = sum(region.metrics[self.metricID] for region in regionlist.values())
        if numDist > 1:
            mean = sumAll/numDist
            m = mean
            s = sumAll
            n = numDist
            a = 1 + 1/(n - 1)
            b = 2*s/(n - 1)
            c = s**2/(n - 1) - n*s**2/40000 - 2*m*s + n*m**2

            # find solution
            posMaxForHalfPercent = abs((-b+sqrt((b**2) - (4*a*c)))/(2*a))
            negMaxForHalfPercent = abs((-b-sqrt((b**2) - (4*a*c)))/(2*a))
            maxRegionMetric = self.__getLargestUnplacedFor().metrics[self.metricID]
            self.maxAcceptableMetric = max(posMaxForHalfPercent, negMaxForHalfPercent, maxRegionMetric)
        else:
            self.maxAcceptableMetric = sumAll

    def isSolved(self):
        return all(placement != 0 for placement in self.placements.values()) and all(district.metric <= self.maxAcceptableMetric for district in self.districts)

    def getStandardDevAsPercent(self):
        metrics = [district.metric for district in self.districts]
        sumAll = sum(metrics)
        return 1 if sumAll == 0 else 100*pstdev(metrics)/sumAll

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
        while any(len(district.regions) == 0 for district in self.districts):
            self.doStep()
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
        curSet = frozenset(self.placements.items())
        self.failures = { failure for failure in self.failures if not curSet <= failure }
        self.failures.add(frozenset(self.placements.items()))

    def __place(self, region, district):
        district.addRegion(region, self.metricID)
        self.placedRegions.append(region)
        self.placements[region.code] = district.index

        for uDistrict in self.unusedDistricts:
            if region in uDistrict.regions:
                isOnlyConnection = not uDistrict.canRemove(region)
                uDistrict.removeRegion(region, self.metricID)
                if len(uDistrict.regions) == 0:
                    self.unusedDistricts.remove(uDistrict)
                if isOnlyConnection:
                    self.unusedDistricts.remove(uDistrict)
                    for newDistrict in self.__getUnusedDistrictsFor(uDistrict.regions):
                        self.unusedDistricts.append(newDistrict)
                return

    def __unplace(self, region = None):
        if region:
            self.placedRegions.remove(region)
        else:
            region = self.placedRegions.pop()
        district = self.__getDistrictFor(region)
        district.removeRegion(region, self.metricID)
        self.placements[region.code] = 0

        return region, district

    def __unplaceSmarter(self):
        district = min(self.districts)

        # Get the difference between the number of neighbors in this and the number of neighbors in the current district
        diffs = { region: district.adj.get(region, 0) - sum(1 for adjCode in region.adj if adjCode in self.__getDistrictFor(region).regions) for region in self.placedRegions }

        # Get the max placed region adjacent to this district which is eligible to be added and at least as connected to this as it is to the district it's leaving
        while not (region := max(filter(lambda region: self.__canAddToDistrict(region, district) and self.__canRemoveFromDistrict(region), self.placedRegions),
                                 key=lambda region: (district.adj.get(region, 0), diffs[region], region.metrics[self.metricID]), default=False)):
            self.__unplace()

        self.__unplace(region)

        return region, district

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
        i = 0
        while i < len(self.unusedDistricts):
            ud = self.unusedDistricts[i]
            adjacentSet = set(ud.adj)
            for d in self.districts:
                # If this unused district's adjacent regions are all in district d, AND there are some adjacent regions (sorry Alaska), add them all!
                if adjacentSet and adjacentSet <= d.regions:
                    if not self.__canAddToDistrict(ud.regions, d, True):
                        return False

                    regionsToPlace = ud.regions.copy()
                    Logger.s("!", d.index, "enclosed {} regions:".format(len(regionsToPlace)), regionsToPlace)
                    for region in regionsToPlace:
                        self.__place(region, d)

                    i -= 1

                    break

            i += 1

        return True

    def __addUnusedClusters(self):
        for district, unused in self.__getUnusedClusters():
            if not self.__canAddToDistrict(unused, district, True):
                return False

            Logger.s("!", district.index, "enclosed {} regions:".format(len(unused)), unused)
            for region in unused:
                self.__place(region, district)

        return True

    # Internal getters ----------------------------------------------------------------------------

    def __canAddToDistrict(self, regions, district, onlyFailures=False):
        if isinstance(regions, Region):
            regions = [regions]
        currState = self.placements.copy()
        runningTally = district.metric
        for region in regions:
            if not onlyFailures and not district.canAdd(region):
                return False
            if not onlyFailures and ((runningTally := runningTally + region.metrics[self.metricID]) > self.maxAcceptableMetric):
                return False
            currState[region.code] = district.index
        return frozenset(currState.items()) not in self.failures

    def __canRemoveFromDistrict(self, regions):
        if isinstance(regions, Region):
            regions = [regions]
        for region in regions:
            district = self.__getDistrictFor(region)
            if not district.canRemove(region):
                return False
        return True

    def __getLargestUnplacedFor(self, district=None):
        if district==None:
            unplaced = (region for region in self.__getUnplacedRegions())
            sorter = lambda region: region.metrics[self.metricID]
        else:
            unplaced = (region for region in self.__getUnplacedRegions() if district.canAdd(region) and self.__canAddToDistrict(region, district))
            sorter = lambda region: (district.adj.get(region.code,0), region.metrics[self.metricID])

        return max(unplaced, key=sorter, default=False)

    def __getNextStarter(self):
        # Get the distances
        minDistances = {}
        metrics = [region.metrics[self.metricID] for region in self.__getUnplacedRegions()]

        # If there are no regions, return False
        if len(metrics) == 0:
            return False

        percentile = pct(metrics, 50)
        district = min(self.districts)
        for region in filter(lambda region: region.metrics[self.metricID] >= percentile and self.__canAddToDistrict(region, district), self.__getUnplacedRegions()):
            reachablePlacedRegions = { inRegion: distanceMatrix[region][inRegion] for inRegion in self.placedRegions if distanceMatrix[region][inRegion] > 0 }
            minDistances[region] = min(reachablePlacedRegions.items(), key=lambda item: item[1], default=("", float("-inf")))

        # If nothing is reachable, just get the biggest unused region
        if all(distance[1] == float("-inf") for distance in minDistances.values()):
            return self.__getLargestUnplacedFor()

        # If we can reach some items, get those items!
        else:
            return max(minDistances, key=lambda region: (minDistances[region][1], region.metrics[self.metricID]), default=False)

    def __getUnusedDistrictsFor(self, regionsToBePlaced):
        # Group unused regions into districts
        while seedRegion := next(iter(regionsToBePlaced), False):
            unusedDistrict = District(0)
            unusedDistrict.addRegion(seedRegion, self.metricID)
            regionsToBePlaced.remove(seedRegion)

            while adjRegion := next(filter(lambda region: unusedDistrict.isAdjacent(region), regionsToBePlaced), False):
                unusedDistrict.addRegion(adjRegion, self.metricID)
                regionsToBePlaced.remove(adjRegion)

            yield unusedDistrict

    def __getUnusedClusters(self):
        for district, border in self.__getBorders():
            if district_unused := self.__getDistrictForBorder(district, border):
                yield district_unused

    def __getDistrictForBorder(self, district, border):
        unusedDist = border.copy()
        unused_iter = iter(unusedDist)
        while seed := next(unused_iter, False):
            while adjRegion := next((regionlist[adjCode] for adjCode in seed.adj if adjCode not in unusedDist and not adjCode in district.regions), False):
                # If this region is in a district other than the bordered one, fail!
                if self.placements[adjRegion] != 0 and self.placements[adjRegion] != district.index:
                    return False
                unusedDist.append(adjRegion)
        return district, unusedDist

    def __getBorders(self):
        for district in self.districts:
            adjUnplaced = [region for region in self.__getUnplacedRegions() if region.code in district.adj]
            while border := Solver.__getBorderFor(adjUnplaced):
                yield district, border

    def __getBorderFor(adjRegions):
        if len(adjRegions) == 0:
            return False

        border = [adjRegions.pop()]
        border_iter = iter(border)
        while seed := next(border_iter, False):
            while adjRegion := next((adjRegion for adjRegion in adjRegions if adjRegion in seed.adj), False):
                adjRegions.remove(adjRegion)
                border.append(adjRegion)
            if len(adjRegions) == 0:
                return border

        return border

    def __getUnplacedRegions(self):
        for region in filter(lambda region: self.placements[region] == 0, self.placements):
            yield region

    def __getDistrictFor(self, region):
        placement = self.placements[region]-1
        if placement in range(len(self.districts)):
            return self.districts[placement]
        else:
            return False

    # Solve it ------------------------------------------------------------------------------------

    def getNextRegion(self):
        self.__updateTime()

        # get the smallest district
        district = min(self.districts)

        self.__updateTime("getMinDistrict")

        # seed - there are no adjacent regions available
        if len(district.adj) == 0 and (region := self.__getNextStarter()):
            self.__updateTime("getSeed")
            return region, district
        # largest adjacent region, or largest neighborless region
        elif region := self.__getLargestUnplacedFor(district):
            self.__updateTime("getUnplaced")
            return region, district
        # else step backwards until we find something we can add to something else!
        else:
            self.__updateTime("selectFailed")
            # Whatever led us to this point failed us - record the failure
            self.__addToFailures()
            return False

    def doStep(self, doStatus = False):
        self.__updateTime()
        # Don't double-dip, and don't perform this if it's solved
        if self.inProgress or self.isSolved():
            return

        self.__updateTime("checkSolved")

        self.inProgress = True

        # If we can't place something...
        if not (tuple := self.getNextRegion()):
            # Unplace the previous one, and get the next region!
            self.__updateTime()
            tuple = self.__unplaceSmarter()
            self.__updateTime("unplace")

        self.__place(*tuple)

        self.__updateTime("place")

        if all(len(district.adj) > 0 for district in self.districts) and not self.isSolved():
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
        print()

#lightUnitTest()
#unitTest(6)
#profile("Solver(4, 3).solve().printConcise()")
#Solver(0, 2).solve(True).printConcise().printSummary()
#Solver(0, 10).getStarters().printConcise()