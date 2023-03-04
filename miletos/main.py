import time as modutime

import os, fnmatch
import sys, datetime
import numpy as np
import pandas as pd
import scipy.interpolate
import scipy.stats

from tqdm import tqdm

from numba import jit, prange

import astroquery

import astropy
import astropy.coordinates
import astropy.units

import pickle
    
import celerite
#from celerite import terms


import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt

#import seaborn as sns

import tdpy
from tdpy.util import summgene

import lygos

import ephesos

"""
Given a target, miletos is an time-domain astronomy tool that allows 
1) automatic search for, download and process TESS and Kepler data via MAST or use user-provided data
2) impose priors based on custom inputs, ExoFOP or NASA Exoplanet Archive
3) model radial velocity and photometric time-series data on N-body systems
4) Make characterization plots of the target after the analysis
"""


def retr_lliknegagpro(listparagpro, lcur, objtgpro):
    '''
    Compute the negative loglikelihood of the GP model
    '''
    
    objtgpro.set_parameter_vector(listparagpro)
    
    return -objtgpro.log_likelihood(lcur)


def retr_gradlliknegagpro(listparagpro, lcur, objtgpro):
    '''
    Compute the gradient of the negative loglikelihood of the GP model
    '''
    
    objtgpro.set_parameter_vector(listparagpro)
    
    return -objtgpro.grad_log_likelihood(lcur)[1]


def retr_tsecpathlocl(tici, typeverb=1):
    '''
    Retrieve the list of TESS sectors for which SPOC light curves are available for target in the local database of predownloaded light curves
    '''
    
    pathbase = os.environ['TESS_DATA_PATH'] + '/data/lcur/'
    path = pathbase + 'tsec/tsec_spoc_%016d.csv' % tici
    if not os.path.exists(path):
        listtsecsele = np.arange(1, 60)
        listpath = []
        listtsec = []
        strgtagg = '*-%016d-*.fits' % tici
        for tsec in listtsecsele:
            pathtemp = pathbase + 'sector-%02d/' % tsec
            listpathtemp = fnmatch.filter(os.listdir(pathtemp), strgtagg)
            
            if len(listpathtemp) > 0:
                listpath.append(pathtemp + listpathtemp[0])
                listtsec.append(tsec)
        
        listtsec = np.array(listtsec).astype(int)
        print('Writing to %s...' % path)
        objtfile = open(path, 'w')
        for k in range(len(listpath)):
            objtfile.write('%d,%s\n' % (listtsec[k], listpath[k]))
        objtfile.close()
    else:
        if typeverb > 0:
            print('Reading from %s...' % path)
        objtfile = open(path, 'r')
        listtsec = []
        listpath = []
        for line in objtfile:
            linesplt = line.split(',')
            listtsec.append(linesplt[0])
            listpath.append(linesplt[1][:-1])
        listtsec = np.array(listtsec).astype(int)
        objtfile.close()
    
    return listtsec, listpath


def retr_listtsectcut(strgmast):
    '''
    Retrieve the list of sectors, cameras, and CCDs for which TESS data are available for the target.
    '''
    
    print('Calling TESSCut with keyword %s to get the list of sectors for which TESS data are available...' % strgmast)
    tabltesscutt = astroquery.mast.Tesscut.get_sectors(coordinates=strgmast, radius=0)

    listtsec = np.array(tabltesscutt['sector'])
    listtcam = np.array(tabltesscutt['camera'])
    listtccd = np.array(tabltesscutt['ccd'])
   
    return listtsec, listtcam, listtccd


def pars_para_mile(para, gdat, strgmodl):
    
    dictparainpt = dict()
    
    gmod = getattr(gdat, strgmodl)
    
    #if gdat.fitt.typemodlenerfitt == 'full':
    #    dictparainpt['consblin'] = para[gmod.dictindxpara['consblin']]
    #else:
    #    for nameparabase in gmod.listnameparabase:
    #        strg = nameparabase + gdat.liststrgdataiter[gdat.indxdataiterthis[0]]
    #        if hasattr(gmod, strg):
    #            dictparainpt[strg] = getattr(gmod, strg)
    #        else:
    #            dictparainpt[strg] = para[gmod.dictindxpara[strg]]
    
    print('gmod.listnameparafullfixd')
    print(gmod.listnameparafullfixd)
    for name in gmod.listnameparafullfixd:
        #print('Found fixed value for parameter %s...' % name)
        dictparainpt[name] = getattr(gmod, name)
    
    print('gmod.listnameparafullvari')
    print(gmod.listnameparafullvari)
    for name in gmod.listnameparafullvari:
        
        dictparainpt[name] = para[gmod.dictindxpara[name]]
        
        if gdat.booldiag:
            if isinstance(gmod.dictindxpara[name], int) and gmod.dictindxpara[name] > 1e6 or \
                        not isinstance(gmod.dictindxpara[name], int) and (gmod.dictindxpara[name] > 1e6).any():
                print('name')
                print(name)
                print('gmod.dictindxpara[name]')
                print(gmod.dictindxpara[name])
                raise Exception('')
    
    if gmod.boolmodlpsys:
        for name in ['radistar', 'masscomp', 'massstar']:
            dictparainpt[name] = None

    if gmod.typemodlblinshap == 'gpro':
        for name in ['sigmgprobase', 'rhoogprobase']:
            dictparainpt[name] = para[gmod.dictindxpara[name]]
    
    raise Exception('')

    return dictparainpt


def retr_dictmodl_mile(gdat, time, dictparainpt, strgmodl):
    
    gmod = getattr(gdat, strgmodl)
    
    dictlistmodl = dict()
    for name in gmod.listnamecompmodl:
        dictlistmodl[name] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    
    if gmod.typemodl == 'flar':
        for p in gdat.indxinst[0]:
            rflxmodl = np.zeros((time[0][p].size, gdat.numbener[p], gmod.numbflar))
            for kk in range(gmod.numbflar):
                strgflar = '%04d' % kk
                timeflar = dictparainpt['timeflar%s' % strgflar]
                amplflar = dictparainpt['amplflar%s' % strgflar]
                tsclflar = dictparainpt['tsclflar%s' % strgflar]

                indxtime = np.where((time[0][p] - timeflar < 10 * tsclflar / 24.) & (timeflar - time[0][p] > -3 * tsclflar / 24.))[0]
                
                # to be deleted
                #if indxtime.size == 0:
                #    print('')
                #    print('time[0][p]')
                #    summgene(time[0][p])
                #    print('timeflar')
                #    print(timeflar)
                #    print('amplflar')
                #    print(amplflar)
                #    print('tsclflar')
                #    print(tsclflar)
                #    print('indxtime')
                #    summgene(indxtime)
                #    print('rflxmodl')
                #    summgene(rflxmodl)
                #    print('time[0][p]')
                #    summgene(time[0][p])
                #    raise Exception('')
                
                if indxtime.size > 0:
                    rflxmodl[indxtime, 0, kk] = amplflar * np.exp(-(time[0][p][indxtime] - timeflar) / tsclflar)
                
            dictlistmodl['sgnl'][0][p] = np.sum(rflxmodl, -1)
    
    timeredu = None
                            
    if gmod.typemodl.startswith('psys') or gmod.typemodl == 'cosc':
        
        timeredu = np.empty(gdat.numbenermodl)
        
        for p in gdat.indxinst[0]:
            if strgmodl == 'fitt' and gdat.fitt.typemodlenerfitt == 'full' or strgmodl == 'true':
                numbener = gdat.numbener[p]
            else:
                numbener = 1
            dictlistmodl['sgnl'][0][p] = np.empty((time[0][p].size, numbener))
        
            dictlistmodl['tran'][0][p] = np.empty_like(dictlistmodl['sgnl'][0][p])
        
        # temp
        pericomp = np.empty(gmod.numbcomp)
        rsmacomp = np.empty(gmod.numbcomp)
        epocmtracomp = np.empty(gmod.numbcomp)
        cosicomp = np.empty(gmod.numbcomp)
        if gmod.typemodl == 'cosc':
            masscomp = np.empty(gmod.numbcomp)
        
        for j in gmod.indxcomp:
            pericomp[j] = dictparainpt['pericom%d' % j]
            rsmacomp[j] = dictparainpt['rsmacom%d' % j]
            epocmtracomp[j] = dictparainpt['epocmtracom%d' % j]
            cosicomp[j] = dictparainpt['cosicom%d' % j]
        if gmod.typemodl == 'cosc':
            for j in gmod.indxcomp:
                masscomp[j] = dictparainpt['masscom%d' % j]
            massstar = dictparainpt['massstar']
            radistar = dictparainpt['massstar']
        else:
            masscomp = None
            massstar = None
            radistar = None
        
        if gdat.booldiag:
            if cosicomp.size != pericomp.size:
                print('')
                print('pericomp')
                summgene(pericomp)
                print('cosicomp')
                summgene(cosicomp)
                raise Exception('')

        for p in gdat.indxinst[0]:
            
            if gmod.boolmodlpsys:
                rratcomp = np.empty((gmod.numbcomp, gdat.numbenerefes))
                if gdat.numbener[p] > 1:
                    rratcomp = np.empty((gmod.numbcomp, gdat.numbeneriter))
                else:
                    rratcomp = np.empty(gmod.numbcomp)
            else:
                rratcomp = None
            
            # limb darkening
            if gmod.typemodllmdkener == 'ener':
                coeflmdk = np.empty((2, gdat.numbener[p]))
                for e in gdat.indxener[p]:
                    coeflmdk[0, e] = dictparainpt['coeflmdklinr' + gdat.liststrgener[p][e]]
                    coeflmdk[1, e] = dictparainpt['coeflmdkquad' + gdat.liststrgener[p][e]]
            elif gmod.typemodllmdkener == 'linr':
                coeflmdk = np.empty((2, gdat.numbener[p]))
            elif gmod.typemodllmdkener == 'cons':
                coeflmdklinr = dictparainpt['coeflmdklinr']
                coeflmdkquad = dictparainpt['coeflmdkquad']
                coeflmdk = np.array([coeflmdklinr, coeflmdkquad])

            if gmod.typemodllmdkener == 'line':
                coeflmdk *= ratiline
            
            if gmod.boolmodlpsys:

                if gdat.numbener[p] > 1:
                    for e in gdat.indxener[p]:
                        for j in gmod.indxcomp:
                            rratcomp[j, e] = np.array([dictparainpt['rratcom%d%s' % (j, gdat.liststrgener[p][e])]])
                else:
                    rratcomp[j] = dictparainpt['rratcom%d' % j]

                dictoutpmodl = ephesos.eval_modl(time[0][p], \
                                                         pericomp=pericomp, \
                                                         epocmtracomp=epocmtracomp, \
                                                         rsmacomp=rsmacomp, \
                                                         cosicomp=cosicomp, \
                                                         
                                                         massstar=massstar, \
                                                         radistar=radistar, \
                                                         masscomp=masscomp, \
                                                         
                                                         typelmdk='quadkipp', \
                                                         
                                                         booldiag=gdat.booldiag, \

                                                         coeflmdk=coeflmdk, \

                                                         typemodllens=gdat.typemodllens, \
                                                         
                                                         rratcomp=rratcomp, \
                                                         typesyst=gmod.typemodl, \
                                                         typeverb=0, \
                                                        )
            
                if gdat.booldiag:
                    if np.amin(dictlistmodl['tran'][0][p]) < 0:
                        raise Exception('')

                print('dictoutpmodl[rflx]')
                summgene(dictoutpmodl['rflx'])
                dictlistmodl['tran'][0][p] = dictoutpmodl['rflx']
                dictlistmodl['sgnl'][0][p] = dictoutpmodl['rflx']
            
            timeredu = dictoutpmodl['timeredu']

    elif gmod.typemodl == 'supn':
        
        
        if gmod.typemodlsupn == 'linr':
            dflxsupn[indxpost] = dictparainpt['coeflinesupn'] * timeoffs[indxpost] * 1e-3
        if gmod.typemodlsupn == 'quad':
            dflxsupn[indxpost] = dictparainpt['coeflinesupn'] * timeoffs[indxpost] * 1e-3 + dictparainpt['coefquadsupn'] * timeoffs[indxpost]**2 * 1e-3
        if gmod.typemodlsupn == 'cubc':
            dflxsupn[indxpost] = dictparainpt['coeflinesupn'] * timeoffs[indxpost] * 1e-3 + dictparainpt['coefquadsupn'] * timeoffs[indxpost]**2 * 1e-3 + \
                                                                                            dictparainpt['coefcubcsupn'] * timeoffs[indxpost]**3 * 1e-3
        for p in gdat.indxinst[0]:
            timeoffs = time[0][p] - dictparainpt['timesupn'] - gdat.timeoffs
            indxpost = np.where(timeoffs > 0)[0]
            dflxsupn = np.zeros_like(time[0][p])
            dictlistmodl['supn'][0][p] = 1. + dflxsupn[:, None]
            dictlistmodl['sgnl'][0][p] = np.copy(dictlistmodl['supn'][0][p])

            if gmod.typemodlexcs == 'bump':
                dictlistmodl['excs'][0][p] = np.ones((time[0][p].size, gdat.numbener[p]))
                if indxpost.size > 0:
                    timeoffs = (time[0][p] - dictparainpt['timesupn'] - dictparainpt['timebumpoffs'] - gdat.timeoffs) / dictparainpt['scalbump']
                    indxpost = np.where(timeoffs > 0)[0]
                    temp = timeoffs[indxpost]**2 * np.exp(-timeoffs[indxpost])
                    temp /= np.amax(temp)
                    dictlistmodl['excs'][0][p][indxpost, 0] += dictparainpt['amplbump'] * temp * 1e-3
                    dictlistmodl['sgnl'][0][p] += dictlistmodl['excs'][0][p] - 1.
        
    # baseline
    if gmod.typemodlblinshap == 'cons':
        for p in gdat.indxinst[0]:
            if strgmodl == 'true' or gdat.fitt.typemodlenerfitt == 'full':
                dictlistmodl['blin'][0][p] = np.empty((time[0][p].size, gdat.numbener[p]))
                if gdat.numbener[p] > 1 and gmod.typemodlblinener[p] == 'ener':
                    for e in gdat.indxener[p]:
                        dictlistmodl['blin'][0][p][:, e] = dictparainpt['consblinener%04d' % e] * 1e-3 * np.ones_like(time[0][p])
                else:
                    dictlistmodl['blin'][0][p][:, 0] = dictparainpt['consblin'] * 1e-3 * np.ones_like(time[0][p])
    
    if gmod.typemodlblinshap == 'step':
        for p in gdat.indxinst[0]:
            rflxbase = np.zeros_like(dictlistmodl['sgnl'][0][p])
            if gdat.fitt.typemodlenerfitt == 'full':
                consfrst = dictparainpt['consblinfrst'][None, :] * 1e-3
                consseco = dictparainpt['consblinseco'][None, :] * 1e-3
                timestep = dictparainpt['timestep'][None, :]
            
            else:
                consfrst = np.full((time[0][p].size, 1), dictparainpt['consblinfrst' + gdat.liststrgdataiter[gdat.indxdataiterthis[0]]]) * 1e-3
                consseco = np.full((time[0][p].size, 1), dictparainpt['consblinseco' + gdat.liststrgdataiter[gdat.indxdataiterthis[0]]]) * 1e-3
                timestep = np.full((time[0][p].size, 1), dictparainpt['timestep' + gdat.liststrgdataiter[gdat.indxdataiterthis[0]]])
                scalstep = np.full((time[0][p].size, 1), dictparainpt['scalstep' + gdat.liststrgdataiter[gdat.indxdataiterthis[0]]])
                
            dictlistmodl['blin'][0][p] = (consseco - consfrst) / (1. + np.exp(-(time[0][p][:, None] - timestep) / scalstep)) + consfrst
        
    if gmod.typemodlblinshap != 'gpro':
        for p in gdat.indxinst[0]:
            print('dictlistmodl[sgnl][0][p]')
            summgene(dictlistmodl['sgnl'][0][p])
            print('dictlistmodl[blin][0][p]')
            summgene(dictlistmodl['blin'][0][p])
            # total model
            dictlistmodl['totl'][0][p] = dictlistmodl['sgnl'][0][p] + dictlistmodl['blin'][0][p] + 1.
            
            # add unity to baseline component
            dictlistmodl['blin'][0][p] += 1.
            
            # add unity to signal component
            dictlistmodl['sgnl'][0][p] += 1.

    #print('strgmodl')
    #print(strgmodl)
    #for name in dictlistmodl.keys():
    #    for b in gdat.indxdatatser:
    #        for p in gdat.indxinst[b]:
    #            print('name')
    #            print(name)
    #            print('dictlistmodl[name][0][p]')
    #            summgene(dictlistmodl[name][0][p])
    #            print('')
    #raise Exception('')

    if gdat.booldiag:
        for name in dictlistmodl.keys():
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if not np.isfinite(dictlistmodl[name][0][p]).all():
                        print('')
                        print('')
                        print('')
                        print('not np.isfinite(dictlistmodl[name][0][p]).all()')
                        print('gmod.typemodlblinshap')
                        print(gmod.typemodlblinshap)
                        print('time[0][p]')
                        summgene(time[0][p])
                        print('name')
                        print(name)
                        print('dictlistmodl[name][0][p]')
                        summgene(dictlistmodl[name][0][p])
                        raise Exception('')
        
    if gdat.booldiag:
        for name in dictlistmodl.keys():
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if dictlistmodl[name][0][p].shape[0] != time[0][p].size:
                        print('')
                        print('')
                        print('')
                        print('dictlistmodl[name][0][p].shape[0] != time[0][p].size')
                        print('name')
                        print(name)
                        print('time[0][p]')
                        summgene(time[0][p])
                        print('dictlistmodl[name][0][p]')
                        summgene(dictlistmodl[name][0][p])
                        raise Exception('')
        
    if gmod.typemodl.startswith('psys') or gmod.typemodl == 'cosc':
        for p in gdat.indxinst[1]:
            dictlistmodl[1][p] = retr_rvel(time[1][p], dictparainpt['epocmtracomp'], dictparainpt['pericomp'], dictparainpt['masscomp'], \
                                                dictparainpt['massstar'], dictparainpt['inclcomp'], dictparainpt['eccecomp'], dictparainpt['argupericomp'])
    
    if gdat.booldiag:
        for namecompmodl in gmod.listnamecompmodl:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if time[b][p].size != dictlistmodl[namecompmodl][b][p].shape[0]:
                        print('')
                        print('')
                        print('')
                        print('')
                        print('namecompmodl')
                        print(namecompmodl)
                        print('dictlistmodl[namecompmodl][b][p]')
                        summgene(dictlistmodl[namecompmodl][b][p])
                        print('time[b][p]')
                        summgene(time[b][p])
                        print('np.unique(gdat.time[b][p])')
                        summgene(np.unique(time[b][p]))
                        raise Exception('')

    return dictlistmodl, timeredu


def retr_rflxmodl_mile_gpro(gdat, strgmodl, timemodl, dictparainpt, timemodleval=None, rflxmodl=None):
    
    dictobjtkern, dictobjtgpro = setp_gpro(gdat, dictparainpt, strgmodl)
    dictmodl = dict()
    for name in gdat.listnamecompgpro:
        if name == 'supn' or name == 'excs':
            timeoffsdata = gdat.timethisfittconc - dictparainpt['timesupn'] - gdat.timeoffs
            timeoffsmodl = timemodl - dictparainpt['timesupn'] - gdat.timeoffs
        if name == 'supn':
            indxtimedata = np.where(timeoffsdata > 0)[0]
            indxtimemodl = np.where(timeoffsmodl > 0)[0]
        if name == 'excs':
            indxtimedata = np.where((timeoffsdata > 0) & (timeoffsdata < 2.))[0]
            indxtimemodl = np.where((timeoffsmodl > 0) & (timeoffsmodl < 2.))[0]
        if name == 'totl':
            indxtimedata = np.arange(gdat.timethisfitt[b][p].size)
            indxtimemodl = np.arange(timemodl.size)
        
        dictmodl[name] = np.ones((timemodl.size, gdat.numbener[p]))
        if timemodleval is not None:
            dictmodleval[name] = np.ones((timemodl.size, gdat.numbener[p]))
        
        if strgmodl == 'true':
            for e in gdat.indxenermodl:
                # compute the covariance matrix
                dictobjtgpro[name].compute(gdat.timethisfitt[b][p][indxtimedata])
                # get the GP model mean baseline
                dictmodl[name][indxtimemodl, e] = 1. + dictobjtgpro[name].sample()
                
        else:
            for e in gdat.indxenermodl:
                # compute the covariance matrix
                dictobjtgpro[name].compute(gdat.timethisfitt[b][p][indxtimedata], yerr=gdat.stdvrflxthisfittsele[indxtimedata, e])
                # get the GP model mean baseline
                dictmodl[name][indxtimemodl, e] = 1. + dictobjtgpro[name].predict(gdat.rflxthisfittsele[indxtimedata, e] - rflxmodl[indxtimedata, e], \
                                                                                                        t=timemodl[indxtimemodl], return_cov=False, return_var=False)
                if timemodleval is not None:
                    pass

    return dictmodl, dictmodleval


def setp_gpro(gdat, dictparainpt, strgmodl):
    
    dictobjtkern = dict()
    dictobjtgpro = dict()

    gmod = getattr(gdat, strgmodl)
    
    ## construct the kernel object
    if gmod.typemodlblinshap == 'gpro':
        dictobjtkern['blin'] = celerite.terms.Matern32Term(log_sigma=np.log(dictparainpt['sigmgprobase']*1e-3), log_rho=np.log(dictparainpt['rhoogprobase']))
    
    k = 0
    #print('strgmodl')
    #print(strgmodl)
    #print('dictobjtkern')
    #print(dictobjtkern)
    for name, valu in dictobjtkern.items():
        if k == 0:
            objtkerntotl = valu
        else:
            objtkerntotl += valu
        k += 1
    if dictobjtkern is not None:
        dictobjtkern['totl'] = objtkerntotl
    
    ## construct the GP model object
    for name in dictobjtkern:
        dictobjtgpro[name] = celerite.GP(dictobjtkern[name])
    
    return dictobjtkern, dictobjtgpro


def retr_llik_mile(para, gdat):
    
    """
    Return the likelihood.
    """
    
    gmod = gdat.fitt
    
    dictparainpt = pars_para_mile(para, gdat, 'fitt')
    dictmodl = retr_dictmodl_mile(gdat, gdat.timethisfitt, dictparainpt, 'fitt')[0]
    
    llik = 0.
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
            
            if gdat.fitt.typemodl == 'supn' and (dictmodl['supn'][b][p] < 1).any():
                return -np.inf
    
            if gdat.fitt.typemodlenerfitt == 'full':
                gdat.rflxthisfittsele = gdat.rflxthisfitt[b][p]
                gdat.varirflxthisfittsele = gdat.varirflxthisfitt[b][p]
                gdat.stdvrflxthisfittsele = gdat.stdvrflxthisfitt[b][p]
            else:
                gdat.rflxthisfittsele = gdat.rflxthisfitt[b][p][:, gdat.fitt.listindxinstener]
                gdat.varirflxthisfittsele = gdat.varirflxthisfitt[b][p][:, gdat.fitt.listindxinstener]
                gdat.stdvrflxthisfittsele = gdat.stdvrflxthisfitt[b][p][:, gdat.fitt.listindxinstener]
            
            if gdat.booldiag:
                if gdat.rflxthisfittsele.ndim != dictmodl['totl'][b][p].ndim:
                    print('')
                    print('gdat.rflxthisfittsele')
                    summgene(gdat.rflxthisfittsele)
                    raise Exception('')
                if gdat.rflxthisfittsele.shape[0] != dictmodl['totl'][b][p].shape[0]:
                    print('')
                    print('gdat.rflxthisfittsele')
                    summgene(gdat.rflxthisfittsele)
                    raise Exception('')
                
            if gdat.typellik == 'gpro':
                
                for e in gdat.indxenermodl:
                    
                    resitemp = gdat.rflxthisfittsele[:, e] - dictmodl['totl'][0][p][:, e]
                    
                    # construct a Gaussian Process (GP) model
                    dictobjtkern, dictobjtgpro = setp_gpro(gdat, dictparainpt, 'fitt')
                
                    # compute the covariance matrix
                    dictobjtgpro['totl'].compute(gdat.timethisfitt[b][p], yerr=gdat.stdvrflxthisfittsele[:, e])
                
                    # get the initial parameters of the GP model
                    #parainit = objtgpro.get_parameter_vector()
                    
                    # get the bounds on the GP model parameters
                    #limtparagpro = objtgpro.get_parameter_bounds()
                    
                    # minimize the negative loglikelihood
                    #objtmini = scipy.optimize.minimize(retr_lliknegagpro, parainit, jac=retr_gradlliknegagpro, method="L-BFGS-B", \
                    #                                                                 bounds=limtparagpro, args=(lcurregi[indxtimeregioutt[i]], objtgpro))
                    
                    #print('GP Matern 3/2 parameters with maximum likelihood:')
                    #print(objtmini.x)

                    # update the GP model with the parameters that minimize the negative loglikelihood
                    #objtgpro.set_parameter_vector(objtmini.x)
                    
                    # get the GP model mean baseline
                    #lcurbase = objtgpro.predict(lcurregi[indxtimeregioutt[i]], t=timeregi, return_cov=False, return_var=False)#[0]
                    
                    # subtract the baseline from the data
                    #lcurbdtrregi[i] = 1. + lcurregi - lcurbase

                    #listobjtspln[i] = objtgpro
                    #gp.compute(gdat.time[0], yerr=gdat.stdvrflxthisfittsele)
                
                    llik += dictobjtgpro['totl'].log_likelihood(resitemp)
                    
                    #print('resitemp')
                    #summgene(resitemp)
                    #print('dictobjtkern')
                    #print(dictobjtkern)

            if gdat.typellik == 'sing':
                
                gdat.lliktemp[b][p] = -0.5 * (gdat.rflxthisfittsele - dictmodl['totl'][b][p])**2 / gdat.varirflxthisfittsele
                
                if gdat.boolrejeoutlllik:
                    #gdat.lliktemp[b][p] = np.sort(gdat.lliktemp.flatten())[1:]
                    gdat.lliktemp[b][p][0, 0] -= np.amin(gdat.lliktemp)
                
            llik += np.sum(gdat.lliktemp[b][p])
    
    if gdat.booldiag:
        if gdat.typellik == 'sing' and llik.size != 1:
            print('gdat.fitt.typemodlenerfitt')
            print(gdat.fitt.typemodlenerfitt)
            print('gdat.rflxthisfittsele')
            summgene(gdat.rflxthisfittsele)
            print('gdat.varirflxthisfittsele')
            summgene(gdat.varirflxthisfittsele)
            print('llik')
            print(llik)
            raise Exception('')
        if not np.isfinite(llik):
            print('')
            print('gdat.typellik')
            print(gdat.typellik)
            print('dictparainpt')
            print(dictparainpt)
            print('gdat.varirflxthisfittsele')
            summgene(gdat.varirflxthisfittsele)
            print('gdat.rflxthisfittsele')
            summgene(gdat.rflxthisfittsele)
            print('gdat.fitt.typemodlenerfitt')
            print(gdat.fitt.typemodlenerfitt)
            raise Exception('')

    return llik


def retr_lliknega_mile(para, gdat):
    
    llik = retr_llik_mile(para, gdat)
    
    return -llik


def retr_dictderi_mile(para, gdat):
    
    gmod = getattr(gdat, gdat.thisstrgmodl)

    dictparainpt = pars_para_mile(para, gdat, 'fitt')

    dictvarbderi = dict()
    dictmodlfine, temp = retr_dictmodl_mile(gdat, gdat.timethisfittfine, dictparainpt, gdat.thisstrgmodl)
    
    dictmodl, dictvarbderi['timeredu'] = retr_dictmodl_mile(gdat, gdat.timethisfitt, dictparainpt, gdat.thisstrgmodl)
    
    #for name in dictrflxmodl:
    #    dictvarbderi['rflxmodl%sfine' % name] = dictrflxmodl[name]
    
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
                
            strg = 'b%03dp%03d' % (b, p)
            
            if gdat.typellik == 'gpro':
                
                dictmodlgprofine = retr_rflxmodl_mile_gpro(gdat, gdat.thisstrgmodl, gdat.timethisfittfine[b][p], dictparainpt, rflxmodl=dictmodlfine['totl'])
                dictmodlgpro = retr_rflxmodl_mile_gpro(gdat, gdat.thisstrgmodl, gdat.timethisfitt[b][p], dictparainpt, rflxmodl=dictmodl['totl'])
                
                dictmodl['gpro'] = dictmodlgpro['totl']
                
                dictmodlfine['totl'] += dictrflx['totl'] - 1.
                dictmodl['totl'] += dictrflxfine['totl'] - 1.
    
            for namecompmodl in gmod.listnamecompmodl:
                dictvarbderi['modlfine%s%s' % (namecompmodl, strg)] = dictmodlfine[namecompmodl][b][p]
                
                if gdat.booldiag:
                    if gdat.timethisfittfine[b][p].size != dictmodlfine[namecompmodl][b][p].size:
                        print('')
                        print('')
                        print('')
                        print('')
                        print('namecompmodl')
                        print(namecompmodl)
                        print('dictmodlfine[namecompmodl][b][p]')
                        summgene(dictmodlfine[namecompmodl][b][p])
                        print('gdat.timethisfittfine[b][p]')
                        summgene(gdat.timethisfittfine[b][p])
                        print('np.unique(gdat.timethisfittfine[b][p])')
                        summgene(np.unique(gdat.timethisfittfine[b][p]))
                        raise Exception('')

            dictvarbderi['resi%s' % strg] = gdat.rflxthisfitt[b][p][:, gdat.fitt.listindxinstener] - dictmodl['totl'][b][p]

            dictvarbderi['stdvresi%s' % strg] = np.empty((gdat.numbrebn, gdat.numbener[p]))
            for k in gdat.indxrebn:
                delt = gdat.listdeltrebn[b][p][k]
                arry = np.zeros((dictvarbderi['resi%s' % strg].shape[0], gdat.numbener, 3))
                arry[:, 0, 0] = gdat.timethisfitt[b][p]
                for e in gdat.indxenermodl:
                    arry[:, e, 1] = dictvarbderi['resi%s' % strg][:, e]
                arryrebn = ephesos.rebn_tser(arry, delt=delt)
                dictvarbderi['stdvresi%s' % strg][k, :] = np.nanstd(arryrebn[:, :, 1], axis=0)
                if gdat.booldiag:
                    for e in gdat.indxenermodl:
                        if not np.isfinite(dictvarbderi['stdvresi%s' % strg][k, e]):
                            print('')
                            print('arry')
                            summgene(arry)
                            print('ephesos.rebn_tser(arry, delt=gdat.listdeltrebn[b][p][k])[:, 1]')
                            summgene(ephesos.rebn_tser(arry, delt=gdat.listdeltrebn[b][p][k])[:, 1])
                            raise Exception('')
    
            if gdat.booldiag:
                if dictvarbderi['modlfinetotl%s' % strg].size != gdat.timethisfittfine[b][p].size:
                    raise Exception('')
    
    return dictvarbderi


def retr_llik_albbepsi(para, gdat):
    
    # Bond albedo
    albb = para[0]
    
    # heat recirculation efficiency
    epsi = para[2]

    psiimodl = (1 - albb)**.25
    #tmptirre = gdat.dictlist['tmptequi'][:, 0] * psiimodl
    tmptirre = gdat.gmeatmptequi * psiimodl
    
    tmptplandayy, tmptplannigh = retr_tmptplandayynigh(tmptirre)
    
    #llik = np.zeros(gdat.numbsamp)
    #llik += -0.5 * (tmptdayy - gdat.dictlist['tmptdayy'][:, 0])**2
    #llik += -0.5 * (tmptnigh - gdat.dictlist['tmptnigh'][:, 0])**2
    #llik += -0.5 * (psiimodl - gdat.listpsii)**2 * 1e6
    #llik = np.sum(llik)
    
    llik = 0.
    llik += -0.5 * (tmptdayy - gdat.gmeatmptdayy)**2 / gdat.gstdtmptdayy**2
    llik += -0.5 * (tmptnigh - gdat.gmeatmptnigh)**2 / gdat.gstdtmptnigh**2
    llik += -0.5 * (psiimodl - gdat.gmeapsii)**2 / gdat.gstdpsii**2 * 1e3
    
    return llik


def retr_modl_spec(gdat, tmpt, booltess=False, strgtype='intg'):
    
    if booltess:
        thpt = scipy.interpolate.interp1d(gdat.meanwlenband, gdat.thptband)(wlen)
    else:
        thpt = 1.
    
    if strgtype == 'intg':
        spec = tdpy.retr_specbbod(tmpt, gdat.meanwlen)
        spec = np.sum(gdat.diffwlen * spec)
    if strgtype == 'diff' or strgtype == 'logt':
        spec = tdpy.retr_specbbod(tmpt, gdat.cntrwlen)
        if strgtype == 'logt':
            spec *= gdat.cntrwlen
    
    return spec


def retr_llik_spec(para, gdat):
    
    tmpt = para[0]
    
    specboloplan = retr_modl_spec(gdat, tmpt, booltess=False, strgtype='intg')
    deptplan = 1e3 * gdat.rratmedi[0]**2 * specboloplan / gdat.specstarintg # [ppt]
    
    llik = -0.5 * np.sum((deptplan - gdat.deptobsd)**2 / gdat.varideptobsd)
    
    return llik


def writ_filealle(gdat, namefile, pathalle, dictalle, dictalledefa, typeverb=1):
    
    listline = []
    # add the lines
    if namefile == 'params.csv':
        listline.append('#name,value,fit,bounds,label,unit\n')
    
    if dictalle is not None:
        for strg, varb in dictalle.items():
            if namefile == 'params.csv':
                line = strg
                for k, varbtemp in enumerate(varb):
                    if varbtemp is not None:
                        line += ',' + varbtemp
                    else:
                        line += ',' + dictalledefa[strg][k]
                line += '\n'
            else:
                line = strg + ',' + varb + '\n'
            listline.append(line)
    for strg, varb in dictalledefa.items():
        if dictalle is None or strg not in dictalle:
            if namefile == 'params.csv':
                line = strg
                for varbtemp in varb:
                    line += ',' + varbtemp
                line += '\n'
            else:
                line = strg + ',' + varb + '\n'
            listline.append(line)
    
    # write
    pathfile = pathalle + namefile
    objtfile = open(pathfile, 'w')
    for line in listline:
        objtfile.write('%s' % line)
    if typeverb > 0:
        print('Writing to %s...' % pathfile)
    objtfile.close()


def get_color(color):

    if isinstance(color, tuple) and len(color) == 3: # already a tuple of RGB values
        return color

    import matplotlib.colors as mplcolors
    
    if color == 'r':
        color = 'red'
    if color == 'g':
        color = 'green'
    if color == 'y':
        color = 'yellow'
    if color == 'c':
        color = 'cyan'
    if color == 'm':
        color = 'magenta'
    if color == 'b':
        color = 'blue'
    if color == 'o':
        color = 'orange'
    hexcolor = mplcolors.cnames[color]

    hexcolor = hexcolor.lstrip('#')
    lv = len(hexcolor)
    
    return tuple(int(hexcolor[i:i + lv // 3], 16)/255. for i in range(0, lv, lv // 3)) # tuple of rgb values


def plot_pser(gdat, strgmodl, strgarry, boolpost=False, typeverb=1):
    
    gmod = getattr(gdat, strgmodl)
    
    for b in gdat.indxdatatser:
        arrypcur = gdat.arrypcur[strgarry]
        arrypcurbindtotl = gdat.arrypcur[strgarry+'bindtotl']
        if strgarry.startswith('prim'):
            arrypcurbindzoom = gdat.arrypcur[strgarry+'bindzoom']
        # plot individual phase curves
        for p in gdat.indxinst[b]:
            for j in gdat.indxcompprio:
                
                path = gdat.pathvisutarg + 'pcurphas_%s_%s_%s_%s_%s.%s' % (gdat.liststrginst[b][p], gdat.liststrgcomp[j], \
                                                                                            strgarry, gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0., 0.3, 0.5, 0.1]})
                if not os.path.exists(path):
                    # phase on the horizontal axis
                    figr, axis = plt.subplots(1, 1, figsize=gdat.figrsizeydob)
                    if b == 0:
                        yerr = None
                    if b == 1:
                        yerr = arrypcur[b][p][j][:, gdat.indxenerclip, 2]
                    print('')
                    print('strgarry')
                    print(strgarry)
                    print('arrypcur[b][p][j]')
                    summgene(arrypcur[b][p][j])
                    print('gdat.indxenerclip')
                    print(gdat.indxenerclip)
                    axis.errorbar(arrypcur[b][p][j][:, gdat.indxenerclip, 0], arrypcur[b][p][j][:, gdat.indxenerclip, 1], \
                                                                yerr=yerr, elinewidth=1, capsize=2, zorder=1, \
                                                                color='grey', alpha=gdat.alphraww, marker='o', ls='', ms=1, rasterized=gdat.boolrastraww)
                    if b == 0:
                        yerr = None
                    if b == 1:
                        yerr = arrypcurbindzoom[b][p][j][:, gdat.indxenerclip, 2]
                    axis.errorbar(arrypcurbindtotl[b][p][j][:, gdat.indxenerclip, 0], arrypcurbindtotl[b][p][j][:, gdat.indxenerclip, 1], \
                                                                                        color=gdat.listcolrcomp[j], elinewidth=1, capsize=2, \
                                                                                                                     zorder=2, marker='o', ls='', ms=3)
                    if gdat.boolwritplan:
                        axis.text(0.9, 0.9, r'\textbf{%s}' % gdat.liststrgcomp[j], \
                                            color=gdat.listcolrcomp[j], va='center', ha='center', transform=axis.transAxes)
                    axis.set_ylabel(gdat.listlabltser[b])
                    axis.set_xlabel('Phase')
                    # overlay the posterior model
                    if boolpost:
                        axis.plot(gdat.arrypcur[strgarry[:4]+'modltotl'+strgarry[-4:]][b][p][j][:, gdat.indxenerclip, 0], \
                                  gdat.arrypcur[strgarry[:4]+'modltotl'+strgarry[-4:]][b][p][j][:, gdat.indxenerclip, 1], color='b', zorder=3)
                    if gdat.listdeptdraw is not None:
                        for k in range(len(gdat.listdeptdraw)):  
                            axis.axhline(1. - 1e-3 * gdat.listdeptdraw[k], ls='-', color='grey')
                    if typeverb > 0:
                        print('Writing to %s...' % path)
                    plt.savefig(path)
                    plt.close()
            
                if strgarry.startswith('prim'):
                    # time on the horizontal axis
                    path = gdat.pathvisutarg + 'pcurtime_%s_%s_%s_%s_%s.%s' % (gdat.liststrginst[b][p], gdat.liststrgcomp[j], \
                                                                                    strgarry, gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.5, 0.2, 0.5, 0.1]})
                    if not os.path.exists(path):
                        figr, axis = plt.subplots(1, 1, figsize=gdat.figrsize)
                        if b == 0:
                            yerr = None
                        if b == 1:
                            yerr = arrypcur[b][p][j][:, gdat.indxenerclip, 2]
                        axis.errorbar(gdat.pericompprio[j] * arrypcur[b][p][j][:, gdat.indxenerclip, 0] * 24., \
                                                             arrypcur[b][p][j][:, gdat.indxenerclip, 1], yerr=yerr, elinewidth=1, capsize=2, \
                                                            zorder=1, color='grey', alpha=gdat.alphraww, marker='o', ls='', ms=1, rasterized=gdat.boolrastraww)
                        if b == 0:
                            yerr = None
                        if b == 1:
                            yerr = arrypcurbindzoom[b][p][j][:, gdat.indxenerclip, 2]
                        
                        if np.isfinite(gdat.duraprio[j]):
                            axis.errorbar(gdat.pericompprio[j] * arrypcurbindzoom[b][p][j][:, gdat.indxenerclip, 0] * 24., \
                                                                 arrypcurbindzoom[b][p][j][:, gdat.indxenerclip, 1], zorder=2, \
                                                                                                        yerr=yerr, elinewidth=1, capsize=2, \
                                                                                                              color=gdat.listcolrcomp[j], marker='o', ls='', ms=3)
                        if boolpost:
                            axis.plot(gdat.pericompprio[j] * 24. * gdat.arrypcur[strgarry[:4]+'modltotl'+strgarry[-4:]][b][p][j][:, gdat.indxenerclip, 0], \
                                                                   gdat.arrypcur[strgarry[:4]+'modltotl'+strgarry[-4:]][b][p][j][:, gdat.indxenerclip, 1], \
                                                                                                                            color='b', zorder=3)
                        if gdat.boolwritplan:
                            axis.text(0.9, 0.9, \
                                            r'\textbf{%s}' % gdat.liststrgcomp[j], color=gdat.listcolrcomp[j], va='center', ha='center', transform=axis.transAxes)
                        axis.set_ylabel(gdat.listlabltser[b])
                        axis.set_xlabel('Time [hours]')
                        if np.isfinite(gdat.duramask[j]):
                            axis.set_xlim([-np.nanmax(gdat.duramask), np.nanmax(gdat.duramask)])
                        if gdat.listdeptdraw is not None:
                            for k in range(len(gdat.listdeptdraw)):  
                                axis.axhline(1. - 1e-3 * gdat.listdeptdraw[k], ls='--', color='grey')
                        plt.subplots_adjust(hspace=0., bottom=0.25, left=0.25)
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        plt.savefig(path)
                        plt.close()
            
            if gmod.numbcomp > 1:
                # plot all phase curves
                path = gdat.pathvisutarg + 'pcurphastotl_%s_%s_%s_%s.%s' % (gdat.liststrginst[b][p], strgarry, \
                                                                                gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                if not os.path.exists(path):
                    figr, axis = plt.subplots(gmod.numbcomp, 1, figsize=gdat.figrsizeydob, sharex=True)
                    if gmod.numbcomp == 1:
                        axis = [axis]
                    for jj, j in enumerate(gdat.indxcompprio):
                        axis[jj].plot(arrypcur[b][p][j][:, gdat.indxenerclip, 0], arrypcur[b][p][j][:, gdat.indxenerclip, 1], color='grey', alpha=gdat.alphraww, \
                                                                                            marker='o', ls='', ms=1, rasterized=gdat.boolrastraww)
                        axis[jj].plot(arrypcurbindtotl[b][p][j][:, gdat.indxenerclip, 0], \
                                            arrypcurbindtotl[b][p][j][:, gdat.indxenerclip, 1], color=gdat.listcolrcomp[j], marker='o', ls='', ms=1)
                        if gdat.boolwritplan:
                            axis[jj].text(0.97, 0.8, r'\textbf{%s}' % gdat.liststrgcomp[j], transform=axis[jj].transAxes, \
                                                                                                color=gdat.listcolrcomp[j], va='center', ha='center')
                    axis[0].set_ylabel(gdat.listlabltser[b])
                    axis[0].set_xlim(-0.5, 0.5)
                    axis[0].yaxis.set_label_coords(-0.08, 1. - 0.5 * gmod.numbcomp)
                    axis[gmod.numbcomp-1].set_xlabel('Phase')
                    
                    plt.subplots_adjust(hspace=0., bottom=0.2)
                    if gdat.typeverb > 0:
                        print('Writing to %s...' % path)
                    plt.savefig(path)
                    plt.close()
    

def retr_albg(amplplanrefl, radicomp, smax):
    '''
    Return geometric albedo.
    '''
    
    albg = amplplanrefl / (radicomp / smax)**2
    
    return albg


def calc_feat(gdat, strgpdfn):

    gdat.liststrgfeat = ['epocmtracomp', 'pericomp', 'rratcomp', 'rsmacomp', 'cosicomp', 'ecos', 'esin', 'rvelsema']
    if strgpdfn == '0003' or strgpdfn == '0004':
        gdat.liststrgfeat += ['sbrtrati', 'amplelli', 'amplbeam']
    if strgpdfn == '0003':
        gdat.liststrgfeat += ['amplplan', 'timeshftplan']
    if strgpdfn == '0004':
        gdat.liststrgfeat += ['amplplanther', 'amplplanrefl', 'timeshftplanther', 'timeshftplanrefl']
    
    gdat.dictlist = {}
    gdat.dictpost = {}
    gdat.dicterrr = {}
    for strgfeat in gdat.liststrgfeat:
        gdat.dictlist[strgfeat] = np.empty((gdat.numbsamp, gmod.numbcomp))

        for j in gmod.indxcomp:
            if strgpdfn == 'prio' or strgpdfn in gdat.typepriocomp:
                mean = getattr(gdat, strgfeat + 'prio')
                stdv = getattr(gdat, 'stdv' + strgfeat + 'prio')
                if not np.isfinite(mean[j]):
                    continue

                gdat.dictlist[strgfeat][:, j] = mean[j] + np.random.randn(gdat.numbsamp) * stdv[j]
                if strgfeat == 'rratcomp':
                    gdat.dictlist[strgfeat][:, j] = tdpy.samp_gaustrun(gdat.numbsamp, mean[j], stdv[j], 0., np.inf)

            else:
                if strgfeat == 'epocmtracomp':
                    strg = '%s_epoch' % gdat.liststrgcomp[j]
                if strgfeat == 'pericomp':
                    strg = '%s_period' % gdat.liststrgcomp[j]
                if strgfeat == 'rratcomp':
                    strg = '%s_rr' % gdat.liststrgcomp[j]
                if strgfeat == 'rsmacomp':
                    strg = '%s_rsuma' % gdat.liststrgcomp[j]
                if strgfeat == 'cosicomp':
                    strg = '%s_cosi' % gdat.liststrgcomp[j]
    
                if strgpdfn == '0003' or strgpdfn == '0004':
                    if strgfeat == 'sbrtrati':
                        strg = '%s_sbratio_TESS' % gdat.liststrgcomp[j]
                    if strgfeat == 'amplbeam':
                        strg = '%s_phase_curve_beaming_TESS' % gdat.liststrgcomp[j]
                    if strgfeat == 'amplelli':
                        strg = '%s_phase_curve_ellipsoidal_TESS' % gdat.liststrgcomp[j]
                if strgpdfn == '0003':
                    if strgfeat == 'amplplan':
                        strg = '%s_phase_curve_atmospheric_TESS' % gdat.liststrgcomp[j]
                    if strgfeat == 'timeshftplan':
                        strg = '%s_phase_curve_atmospheric_shift_TESS' % gdat.liststrgcomp[j]
                if strgpdfn == '0004':
                    if strgfeat == 'amplplanther':
                        strg = '%s_phase_curve_atmospheric_thermal_TESS' % gdat.liststrgcomp[j]
                    if strgfeat == 'amplplanrefl':
                        strg = '%s_phase_curve_atmospheric_reflected_TESS' % gdat.liststrgcomp[j]
                    if strgfeat == 'timeshftplanther':
                        strg = '%s_phase_curve_atmospheric_thermal_shift_TESS' % gdat.liststrgcomp[j]
                    if strgfeat == 'timeshftplanrefl':
                        strg = '%s_phase_curve_atmospheric_reflected_shift_TESS' % gdat.liststrgcomp[j]
            
                if strg in gdat.objtalle[strgpdfn].posterior_params.keys():
                    gdat.dictlist[strgfeat][:, j] = gdat.objtalle[strgpdfn].posterior_params[strg][gdat.indxsamp]
                else:
                    gdat.dictlist[strgfeat][:, j] = np.zeros(gdat.numbsamp) + allesfitter.config.BASEMENT.params[strg]

    if gdat.typeverb > 0:
        print('Calculating derived variables...')
    # derived variables
    ## get samples from the star's variables

    # stellar features
    for featstar in gdat.listfeatstar:
        meantemp = getattr(gdat, featstar)
        stdvtemp = getattr(gdat, 'stdv' + featstar)
        
        # not a specific host star
        if meantemp is None:
            continue

        if not np.isfinite(meantemp):
            if gdat.typeverb > 0:
                print('Stellar feature %s is not finite!' % featstar)
                print('featstar')
                print(featstar)
                print('meantemp')
                print(meantemp)
                print('stdvtemp')
                print(stdvtemp)
            gdat.dictlist[featstar] = np.empty(gdat.numbsamp) + np.nan
        elif stdvtemp == 0.:
            gdat.dictlist[featstar] = meantemp + np.zeros(gdat.numbsamp)
        else:
            gdat.dictlist[featstar] = tdpy.samp_gaustrun(gdat.numbsamp, meantemp, stdvtemp, 0., np.inf)
        
        gdat.dictlist[featstar] = np.vstack([gdat.dictlist[featstar]] * gmod.numbcomp).T
    
    # inclination [degree]
    gdat.dictlist['incl'] = np.arccos(gdat.dictlist['cosicomp']) * 180. / np.pi
    
    # log g of the host star
    gdat.dictlist['loggstar'] = gdat.dictlist['massstar'] / gdat.dictlist['radistar']**2

    gdat.dictlist['ecce'] = gdat.dictlist['esin']**2 + gdat.dictlist['ecos']**2
    
    if gmod.boolmodlpsys:
        # radius of the planets
        gdat.dictlist['radicomp'] = gdat.dictfact['rsre'] * gdat.dictlist['radistar'] * gdat.dictlist['rratcomp'] # [R_E]
    
        # semi-major axis
        gdat.dictlist['smax'] = (gdat.dictlist['radicomp'] + gdat.dictlist['radistar']) / gdat.dictlist['rsmacomp']
    
        if strgpdfn == '0003' or strgpdfn == '0004':
            gdat.dictlist['amplnigh'] = gdat.dictlist['sbrtrati'] * gdat.dictlist['rratcomp']**2
        if strgpdfn == '0003':
            gdat.dictlist['phasshftplan'] = gdat.dictlist['timeshftplan'] * 360. / gdat.dictlist['pericomp']
        if strgpdfn == '0004':
            gdat.dictlist['phasshftplanther'] = gdat.dictlist['timeshftplanther'] * 360. / gdat.dictlist['pericomp']
            gdat.dictlist['phasshftplanrefl'] = gdat.dictlist['timeshftplanrefl'] * 360. / gdat.dictlist['pericomp']

        # planet equilibrium temperature
        gdat.dictlist['tmptplan'] = gdat.dictlist['tmptstar'] * np.sqrt(gdat.dictlist['radistar'] / 2. / gdat.dictlist['smax'])
        
        # stellar luminosity
        gdat.dictlist['lumistar'] = gdat.dictlist['radistar']**2 * (gdat.dictlist['tmptstar'] / 5778.)**4
        
        # insolation
        gdat.dictlist['inso'] = gdat.dictlist['lumistar'] / gdat.dictlist['smax']**2
    
        # predicted planet mass
        if gdat.typeverb > 0:
            print('Calculating predicted masses...')
        
        gdat.dictlist['masscomppred'] = np.full_like(gdat.dictlist['radicomp'], np.nan)
        gdat.dictlist['masscomppred'] = ephesos.retr_massfromradi(gdat.dictlist['radicomp'])
        gdat.dictlist['masscomppred'] = gdat.dictlist['masscomppred']
        
        # mass used for later calculations
        gdat.dictlist['masscompused'] = np.empty_like(gdat.dictlist['masscomppred'])
        
        # temp
        gdat.dictlist['masscomp'] = np.zeros_like(gdat.dictlist['esin'])
        gdat.dictlist['masscompused'] = gdat.dictlist['masscomppred']
        #for j in gmod.indxcomp:
        #    if 
        #        gdat.dictlist['masscompused'][:, j] = 
        #    else:
        #        gdat.dictlist['masscompused'][:, j] = 
    
        # density of the planet
        gdat.dictlist['densplan'] = gdat.dictlist['masscompused'] / gdat.dictlist['radicomp']**3

        # escape velocity
        gdat.dictlist['vesc'] = ephesos.retr_vesc(gdat.dictlist['masscompused'], gdat.dictlist['radicomp'])
        
        for j in gmod.indxcomp:
            strgratiperi = 'ratiperi_%s' % gdat.liststrgcomp[j]
            strgratiradi = 'ratiradi_%s' % gdat.liststrgcomp[j]
            for jj in gmod.indxcomp:
                gdat.dictlist[strgratiperi] = gdat.dictlist['pericomp'][:, j] / gdat.dictlist['pericomp'][:, jj]
                gdat.dictlist[strgratiradi] = gdat.dictlist['radicomp'][:, j] / gdat.dictlist['radicomp'][:, jj]
    
        gdat.dictlist['depttrancomp'] = 1e3 * gdat.dictlist['rratcomp']**2 # [ppt]
        # TSM
        gdat.dictlist['tsmm'] = ephesos.retr_tsmm(gdat.dictlist['radicomp'], gdat.dictlist['tmptplan'], \
                                                                                    gdat.dictlist['masscompused'], gdat.dictlist['radistar'], gdat.jmagsyst)
        
        # ESM
        gdat.dictlist['esmm'] = ephesos.retr_esmm(gdat.dictlist['tmptplan'], gdat.dictlist['tmptstar'], \
                                                                                    gdat.dictlist['radicomp'], gdat.dictlist['radistar'], gdat.kmagsyst)
        
    else:
        # semi-major axis
        gdat.dictlist['smax'] = (gdat.dictlist['radistar']) / gdat.dictlist['rsmacomp']
    
    # temp
    gdat.dictlist['sini'] = np.sqrt(1. - gdat.dictlist['cosicomp']**2)
    gdat.dictlist['omeg'] = 180. / np.pi * np.mod(np.arctan2(gdat.dictlist['esin'], gdat.dictlist['ecos']), 2 * np.pi)
    gdat.dictlist['rs2a'] = gdat.dictlist['rsmacomp'] / (1. + gdat.dictlist['rratcomp'])
    gdat.dictlist['sinw'] = np.sin(np.pi / 180. * gdat.dictlist['omeg'])
    gdat.dictlist['imfa'] = ephesos.retr_imfa(gdat.dictlist['cosicomp'], gdat.dictlist['rs2a'], gdat.dictlist['ecce'], gdat.dictlist['sinw'])
   
    # RV semi-amplitude
    gdat.dictlist['rvelsemapred'] = ephesos.retr_rvelsema(gdat.dictlist['pericomp'], gdat.dictlist['masscomppred'], \
                                                                        gdat.dictlist['massstar'], gdat.dictlist['incl'], gdat.dictlist['ecce'])
    
    ## expected Doppler beaming (DB)
    deptbeam = 1e3 * 4. * gdat.dictlist['rvelsemapred'] / 3e8 * gdat.consbeam # [ppt]

    ## expected ellipsoidal variation (EV)
    ## limb and gravity darkening coefficients from Claret2017
    if gdat.typeverb > 0:
        print('temp: connect these to Claret2017')
    # linear limb-darkening coefficient
    coeflidaline = 0.4
    # gravitational darkening coefficient
    coefgrda = 0.2
    alphelli = ephesos.retr_alphelli(coeflidaline, coefgrda)
    gdat.dictlist['deptelli'] = 1e3 * alphelli * gdat.dictlist['masscompused'] * np.sin(gdat.dictlist['incl'] / 180. * np.pi)**2 / \
                                                                  gdat.dictlist['massstar'] * (gdat.dictlist['radistar'] / gdat.dictlist['smax'])**3 # [ppt]
    if gdat.typeverb > 0:
        print('Calculating durations...')
                      
    gdat.dictlist['duratranfull'] = ephesos.retr_duratranfull(gdat.dictlist['pericomp'], gdat.dictlist['rsmacomp'], gdat.dictlist['cosicomp'], gdat.dictlist['rratcomp'])
    gdat.dictlist['duratrantotl'] = ephesos.retr_duratrantotl(gdat.dictlist['pericomp'], gdat.dictlist['rsmacomp'], gdat.dictlist['cosicomp'])
    
    gdat.dictlist['maxmdeptblen'] = 1e3 * (1. - gdat.dictlist['duratranfull'] / gdat.dictlist['duratrantotl'])**2 / \
                                                                    (1. + gdat.dictlist['duratranfull'] / gdat.dictlist['duratrantotl'])**2 # [ppt]
    gdat.dictlist['minmdilu'] = gdat.dictlist['depttrancomp'] / gdat.dictlist['maxmdeptblen']
    gdat.dictlist['minmratiflux'] = gdat.dictlist['minmdilu'] / (1. - gdat.dictlist['minmdilu'])
    gdat.dictlist['maxmdmag'] = -2.5 * np.log10(gdat.dictlist['minmratiflux'])
    
    # orbital
    ## RM effect
    gdat.dictlist['amplrmef'] = 2. / 3. * gdat.dictlist['vsiistar'] * 1e-3 * gdat.dictlist['depttrancomp'] * np.sqrt(1. - gdat.dictlist['imfa'])
    gdat.dictlist['stnormefpfss'] = (gdat.dictlist['amplrmef'] / 0.9) * np.sqrt(gdat.dictlist['duratranfull'] / (10. / 60. / 24.))
    
    # 0003 single component, offset
    # 0004 double component, offset
    if strgpdfn == '0003':
        frac = np.random.rand(gdat.dictlist['amplplan'].size).reshape(gdat.dictlist['amplplan'].shape)
        gdat.dictlist['amplplanther'] = gdat.dictlist['amplplan'] * frac
        gdat.dictlist['amplplanrefl'] = gdat.dictlist['amplplan'] * (1. - frac)
    
    if strgpdfn == '0004':
        # temp -- this does not work for two component (thermal + reflected)
        gdat.dictlist['amplseco'] = gdat.dictlist['amplnigh'] + gdat.dictlist['amplplanther'] + gdat.dictlist['amplplanrefl']
    if strgpdfn == '0003':
        # temp -- this does not work when phase shift is nonzero
        gdat.dictlist['amplseco'] = gdat.dictlist['amplnigh'] + gdat.dictlist['amplplan']
    
    if strgpdfn == '0003' or strgpdfn == '0004':
        gdat.dictlist['albg'] = retr_albg(gdat.dictlist['amplplanrefl'], gdat.dictlist['radicomp'], gdat.dictlist['smax'])

    if gdat.typeverb > 0:
        print('Calculating the equilibrium temperature of the planets...')
    
    gdat.dictlist['tmptequi'] = gdat.dictlist['tmptstar'] * np.sqrt(gdat.dictlist['radistar'] / gdat.dictlist['smax'] / 2.)
    
    if False and gdat.labltarg == 'WASP-121' and strgpdfn != 'prio':
        
        # read and parse ATMO posterior
        ## get secondary depth data from Tom
        path = gdat.pathdatatarg + 'ascii_output/EmissionDataArray.txt'
        print('Reading from %s...' % path)
        arrydata = np.loadtxt(path)
        print('arrydata')
        summgene(arrydata)
        print('arrydata[0, :]')
        print(arrydata[0, :])
        path = gdat.pathdatatarg + 'ascii_output/EmissionModelArray.txt'
        print('Reading from %s...' % path)
        arrymodl = np.loadtxt(path)
        print('arrymodl')
        summgene(arrymodl)
        print('Secondary eclipse depth mean and standard deviation:')
        # get wavelengths
        path = gdat.pathdatatarg + 'ascii_output/ContribFuncWav.txt'
        print('Reading from %s...' % path)
        wlen = np.loadtxt(path)
        path = gdat.pathdatatarg + 'ascii_output/ContribFuncWav.txt'
        print('Reading from %s...' % path)
        wlenctrb = np.loadtxt(path, skiprows=1)
   
        ### spectrum of the host star
        gdat.meanwlenthomraww = arrymodl[:, 0]
        gdat.specstarthomraww = arrymodl[:, 9]
        
        ## calculate the geometric albedo "informed" by the ATMO posterior
        wlenmodl = arrymodl[:, 0]
        deptmodl = arrymodl[:, 1]
        indxwlenmodltess = np.where((wlenmodl > 0.6) & (wlenmodl < 0.95))[0]
        gdat.amplplantheratmo = np.mean(deptmodl[indxwlenmodltess])
        gdat.dictlist['amplplanreflatmo'] = 1e-6 * arrydata[0, 2] + np.random.randn(gdat.numbsamp).reshape((gdat.numbsamp, 1)) \
                                                                                                    * arrydata[0, 3] * 1e-6 - gdat.amplplantheratmo
        #gdat.dictlist['amplplanreflatmo'] = gdat.dictlist['amplplan'] - gdat.amplplantheratmo
        gdat.dictlist['albginfo'] = retr_albg(gdat.dictlist['amplplanreflatmo'], gdat.dictlist['radicomp'], gdat.dictlist['smax'])
        
        ## update Tom's secondary (dayside) with the posterior secondary depth, since Tom's secondary was preliminary (i.e., 490+-50 ppm)
        print('Updating the multiband depth array with dayside and adding the nightside...')
        medideptseco = np.median(gdat.dictlist['amplseco'][:, 0])
        stdvdeptseco = (np.percentile(gdat.dictlist['amplseco'][:, 0], 84.) - np.percentile(gdat.dictlist['amplseco'][:, 0], 16.)) / 2.
        arrydata[0, 2] = medideptseco * 1e3 # [ppm]
        arrydata[0, 3] = stdvdeptseco * 1e3 # [ppm]
        
        ## add the nightside depth
        medideptnigh = np.median(gdat.dictlist['amplnigh'][:, 0])
        stdvdeptnigh = (np.percentile(gdat.dictlist['amplnigh'][:, 0], 84.) - np.percentile(gdat.dictlist['amplnigh'][:, 0], 16.)) / 2.
        arrydata = np.concatenate((arrydata, np.array([[arrydata[0, 0], arrydata[0, 1], medideptnigh * 1e3, stdvdeptnigh * 1e6, 0, 0, 0, 0]])), axis=0) # [ppm]
        
        # calculate brightness temperatures
        gmod.listlablpara = [['Temperature', 'K']]
        gdat.rratmedi = np.median(gdat.dictlist['rratcomp'], axis=0)
        listscalpara = ['self']
        gmod.listminmpara = np.array([1000.])
        gmod.listmaxmpara = np.array([4000.])
        meangauspara = None
        stdvgauspara = None
        numbpara = len(gmod.listlablpara)
        numbsampwalk = 1000
        numbsampburnwalk = 5
        gdat.numbdatatmpt = arrydata.shape[0]
        gdat.indxdatatmpt = np.arange(gdat.numbdatatmpt)
        listtmpt = []
        specarry = np.empty((2, 3, gdat.numbdatatmpt))
        for k in gdat.indxdatatmpt:
            
            if not (k == 0 or k == gdat.numbdatatmpt - 1):
                continue
            gdat.minmwlen = arrydata[k, 0] - arrydata[k, 1]
            gdat.maxmwlen = arrydata[k, 0] + arrydata[k, 1]
            gdat.binswlen = np.linspace(gdat.minmwlen, gdat.maxmwlen, 100)
            gdat.meanwlen = (gdat.binswlen[1:] + gdat.binswlen[:-1]) / 2.
            gdat.diffwlen = (gdat.binswlen[1:] - gdat.binswlen[:-1]) / 2.
            gdat.cntrwlen = np.mean(gdat.meanwlen)
            strgextn = 'tmpt_%d' % k
            gdat.indxenerdata = k

            gdat.specstarintg = retr_modl_spec(gdat, gdat.tmptstar, strgtype='intg')
            
            gdat.specstarthomlogt = scipy.interpolate.interp1d(gdat.meanwlenthomraww, gdat.specstarthomraww)(gdat.cntrwlen)
            gdat.specstarthomdiff = gdat.specstarthomlogt / gdat.cntrwlen
            gdat.specstarthomintg = np.sum(gdat.diffwlen * \
                                    scipy.interpolate.interp1d(gdat.meanwlenthomraww, gdat.specstarthomraww)(gdat.meanwlen) / gdat.meanwlen)

            gdat.deptobsd = arrydata[k, 2]
            gdat.stdvdeptobsd = arrydata[k, 3]
            gdat.varideptobsd = gdat.stdvdeptobsd**2
            listtmpttemp = tdpy.samp(gdat, gdat.pathalle[strgpdfn], numbsampwalk, \
                                          retr_llik_spec, \
                                          gmod.listlablpara, listscalpara, gmod.listminmpara, gmod.listmaxmpara, meangauspara, stdvgauspara, numbdata, strgextn=strgextn, \
                                          pathbase=gdat.pathtargruns, \
                                          typeverb=gdat.typeverb, \
                                          numbsampburnwalk=numbsampburnwalk, boolplot=gdat.boolplot, \
                             )
            listtmpt.append(listtmpttemp)
        listtmpt = np.vstack(listtmpt).T
        indxsamp = np.random.choice(np.arange(listtmpt.shape[0]), size=gdat.numbsamp, replace=False)
        # dayside and nightside temperatures to be used for albedo and circulation efficiency calculation
        gdat.dictlist['tmptdayy'] = listtmpt[indxsamp, 0, None]
        gdat.dictlist['tmptnigh'] = listtmpt[indxsamp, -1, None]
        # dayside/nightside temperature contrast
        gdat.dictlist['tmptcont'] = (gdat.dictlist['tmptdayy'] - gdat.dictlist['tmptnigh']) / gdat.dictlist['tmptdayy']
        
    # copy the prior
    gdat.dictlist['projoblq'] = np.random.randn(gdat.numbsamp)[:, None] * gdat.stdvprojoblqprio[None, :] + gdat.projoblqprio[None, :]
    
    gdat.boolsampbadd = np.zeros(gdat.numbsamp, dtype=bool)
    for j in gmod.indxcomp:
        boolsampbaddtemp = ~np.isfinite(gdat.dictlist['maxmdmag'][:, j])
        gdat.boolsampbadd = gdat.boolsampbadd | boolsampbaddtemp
    gdat.indxsampbadd = np.where(gdat.boolsampbadd)[0]
    gdat.indxsamptran = np.setdiff1d(gdat.indxsamp, gdat.indxsampbadd)

    gdat.liststrgfeat = np.array(list(gdat.dictlist.keys()))
    for strgfeat in gdat.liststrgfeat:
        errrshap = list(gdat.dictlist[strgfeat].shape)
        errrshap[0] = 3
        gdat.dictpost[strgfeat] = np.empty(errrshap)
        gdat.dicterrr[strgfeat] = np.empty(errrshap)
        
        # transit duration can be NaN when not transiting
        gdat.dictpost[strgfeat][0, ...] = np.nanpercentile(gdat.dictlist[strgfeat], 16., 0)
        gdat.dictpost[strgfeat][1, ...] = np.nanpercentile(gdat.dictlist[strgfeat], 50., 0)
        gdat.dictpost[strgfeat][2, ...] = np.nanpercentile(gdat.dictlist[strgfeat], 84., 0)
        gdat.dicterrr[strgfeat][0, ...] = gdat.dictpost[strgfeat][1, ...]
        gdat.dicterrr[strgfeat][1, ...] = gdat.dictpost[strgfeat][1, ...] - gdat.dictpost[strgfeat][0, ...]
        gdat.dicterrr[strgfeat][2, ...] = gdat.dictpost[strgfeat][2, ...] - gdat.dictpost[strgfeat][1, ...]
        
    # augment
    gdat.dictfeatobjt['radistar'] = gdat.dicterrr['radistar'][0, :]
    gdat.dictfeatobjt['radicomp'] = gdat.dicterrr['radicomp'][0, :]
    gdat.dictfeatobjt['masscomp'] = gdat.dicterrr['masscomp'][0, :]
    gdat.dictfeatobjt['stdvradistar'] = np.mean(gdat.dicterrr['radistar'][1:, :], 0)
    gdat.dictfeatobjt['stdvmassstar'] = np.mean(gdat.dicterrr['massstar'][1:, :], 0)
    gdat.dictfeatobjt['stdvtmptstar'] = np.mean(gdat.dicterrr['tmptstar'][1:, :], 0)
    gdat.dictfeatobjt['stdvloggstar'] = np.mean(gdat.dicterrr['loggstar'][1:, :], 0)
    gdat.dictfeatobjt['stdvradicomp'] = np.mean(gdat.dicterrr['radicomp'][1:, :], 0)
    gdat.dictfeatobjt['stdvmasscomp'] = np.mean(gdat.dicterrr['masscomp'][1:, :], 0)
    gdat.dictfeatobjt['stdvtmptplan'] = np.mean(gdat.dicterrr['tmptplan'][1:, :], 0)
    gdat.dictfeatobjt['stdvesmm'] = np.mean(gdat.dicterrr['esmm'][1:, :], 0)
    gdat.dictfeatobjt['stdvtsmm'] = np.mean(gdat.dicterrr['tsmm'][1:, :], 0)
    

def proc_alle(gdat, typemodl):
    
    #_0003: single component offset baseline
    #_0004: multiple components, offset baseline
        
    if gdat.typeverb > 0:
        print('Processing allesfitter model %s...' % typemodl)
    # allesfit run folder
    gdat.pathalle[typemodl] = gdat.pathallebase + 'allesfit_%s/' % typemodl
    
    # make sure the folder exists
    cmnd = 'mkdir -p %s' % gdat.pathalle[typemodl]
    os.system(cmnd)
    
    # write the input data file
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
            path = gdat.pathalle[typemodl] + gdat.liststrginst[b][p] + '.csv'
            if not os.path.exists(path):
            
                if gdat.boolinfefoldbind:
                    listarrytserbdtrtemp = np.copy(gdat.arrypcur['primbdtrbindtotl'][b][p][0])
                    listarrytserbdtrtemp[:, 0] *= gdat.pericompprio[0]
                    listarrytserbdtrtemp[:, 0] += gdat.epocmtracompprio[0]
                else:
                    listarrytserbdtrtemp = gdat.arrytser['bdtr'][b][p]
                
                # make sure the data are time-sorted
                #indx = np.argsort(listarrytserbdtrtemp[:, 0])
                #listarrytserbdtrtemp = listarrytserbdtrtemp[indx, :]
                    
                if gdat.typeverb > 0:
                    print('Writing to %s...' % path)
                np.savetxt(path, listarrytserbdtrtemp, delimiter=',', header='time,%s,%s_err' % (gdat.liststrgtsercsvv[b], gdat.liststrgtsercsvv[b]))
    
    ## params_star
    pathparastar = gdat.pathalle[typemodl] + 'params_star.csv'
    if not os.path.exists(pathparastar):
        objtfile = open(pathparastar, 'w')
        objtfile.write('#R_star,R_star_lerr,R_star_uerr,M_star,M_star_lerr,M_star_uerr,Teff_star,Teff_star_lerr,Teff_star_uerr\n')
        objtfile.write('#R_sun,R_sun,R_sun,M_sun,M_sun,M_sun,K,K,K\n')
        objtfile.write('%g,%g,%g,%g,%g,%g,%g,%g,%g' % (gdat.radistar, gdat.stdvradistar, gdat.stdvradistar, \
                                                       gdat.massstar, gdat.stdvmassstar, gdat.stdvmassstar, \
                                                                                                      gdat.tmptstar, gdat.stdvtmptstar, gdat.stdvtmptstar))
        if gdat.typeverb > 0:
            print('Writing to %s...' % pathparastar)
        objtfile.close()

    ## params
    dictalleparadefa = dict()
    pathpara = gdat.pathalle[typemodl] + 'params.csv'
    if not os.path.exists(pathpara):
        cmnd = 'touch %s' % (pathpara)
        print(cmnd)
        os.system(cmnd)
    
        for j in gmod.indxcomp:
            strgrrat = '%s_rr' % gdat.liststrgcomp[j]
            strgrsma = '%s_rsuma' % gdat.liststrgcomp[j]
            strgcosi = '%s_cosi' % gdat.liststrgcomp[j]
            strgepoc = '%s_epoch' % gdat.liststrgcomp[j]
            strgperi = '%s_period' % gdat.liststrgcomp[j]
            strgecos = '%s_f_c' % gdat.liststrgcomp[j]
            strgesin = '%s_f_s' % gdat.liststrgcomp[j]
            strgrvelsema = '%s_K' % gdat.liststrgcomp[j]
            dictalleparadefa[strgrrat] = ['%f' % gdat.rratcompprio[j], '1', 'uniform 0 %f' % (4 * gdat.rratcompprio[j]), \
                                                                            '$R_{%s} / R_\star$' % gdat.liststrgcomp[j], '']
            
            dictalleparadefa[strgrsma] = ['%f' % gdat.rsmacompprio[j], '1', 'uniform 0 %f' % (4 * gdat.rsmacompprio[j]), \
                                                                      '$(R_\star + R_{%s}) / a_{%s}$' % (gdat.liststrgcomp[j], gdat.liststrgcomp[j]), '']
            dictalleparadefa[strgcosi] = ['%f' % gdat.cosicompprio[j], '1', 'uniform 0 %f' % max(0.1, 4 * gdat.cosicompprio[j]), \
                                                                                        '$\cos{i_{%s}}$' % gdat.liststrgcomp[j], '']
            dictalleparadefa[strgepoc] = ['%f' % gdat.epocmtracompprio[j], '1', \
                             'uniform %f %f' % (gdat.epocmtracompprio[j] - gdat.stdvepocmtracompprio[j], gdat.epocmtracompprio[j] + gdat.stdvepocmtracompprio[j]), \
                                                                    '$T_{0;%s}$' % gdat.liststrgcomp[j], '$\mathrm{BJD}$']
            dictalleparadefa[strgperi] = ['%f' % gdat.pericompprio[j], '1', \
                                     'uniform %f %f' % (gdat.pericompprio[j] - 3. * gdat.stdvpericompprio[j], gdat.pericompprio[j] + 3. * gdat.stdvpericompprio[j]), \
                                                                    '$P_{%s}$' % gdat.liststrgcomp[j], 'days']
            dictalleparadefa[strgecos] = ['%f' % gdat.ecoscompprio[j], '0', 'uniform -0.9 0.9', \
                                                                '$\sqrt{e_{%s}} \cos{\omega_{%s}}$' % (gdat.liststrgcomp[j], gdat.liststrgcomp[j]), '']
            dictalleparadefa[strgesin] = ['%f' % gdat.esincompprio[j], '0', 'uniform -0.9 0.9', \
                                                                '$\sqrt{e_{%s}} \sin{\omega_{%s}}$' % (gdat.liststrgcomp[j], gdat.liststrgcomp[j]), '']
            dictalleparadefa[strgrvelsema] = ['%f' % gdat.rvelsemaprio[j], '0', \
                               'uniform %f %f' % (max(0, gdat.rvelsemaprio[j] - 5 * gdat.stdvrvelsemaprio[j]), gdat.rvelsemaprio[j] + 5 * gdat.stdvrvelsemaprio[j]), \
                                                                '$K_{%s}$' % gdat.liststrgcomp[j], '']
            if typemodl == '0003' or typemodl == '0004':
                for b in gdat.indxdatatser:
                    if b != 0:
                        continue
                    for p in gdat.indxinst[b]:
                        strgsbrt = '%s_sbratio_' % gdat.liststrgcomp[j] + gdat.liststrginst[b][p]
                        dictalleparadefa[strgsbrt] = ['1e-3', '1', 'uniform 0 1', '$J_{%s; \mathrm{%s}}$' % \
                                                                            (gdat.liststrgcomp[j], gdat.listlablinst[b][p]), '']
                        
                        dictalleparadefa['%s_phase_curve_beaming_%s' % (gdat.liststrgcomp[j], gdat.liststrginst[b][p])] = \
                                             ['0', '1', 'uniform 0 10', '$A_\mathrm{beam; %s; %s}$' % (gdat.liststrgcomp[j], gdat.listlablinst[b][p]), '']
                        dictalleparadefa['%s_phase_curve_atmospheric_%s' % (gdat.liststrgcomp[j], gdat.liststrginst[b][p])] = \
                                             ['0', '1', 'uniform 0 10', '$A_\mathrm{atmo; %s; %s}$' % (gdat.liststrgcomp[j], gdat.listlablinst[b][p]), '']
                        dictalleparadefa['%s_phase_curve_ellipsoidal_%s' % (gdat.liststrgcomp[j], gdat.liststrginst[b][p])] = \
                                             ['0', '1', 'uniform 0 10', '$A_\mathrm{elli; %s; %s}$' % (gdat.liststrgcomp[j], gdat.listlablinst[b][p]), '']

            if typemodl == '0003':
                for b in gdat.indxdatatser:
                    if b != 0:
                        continue
                    for p in gdat.indxinst[b]:
                        maxmshft = 0.25 * gdat.pericompprio[j]
                        minmshft = -maxmshft

                        dictalleparadefa['%s_phase_curve_atmospheric_shift_%s' % (gdat.liststrgcomp[j], gdat.liststrginst[b][p])] = \
                                         ['0', '1', 'uniform %.3g %.3g' % (minmshft, maxmshft), \
                                            '$\Delta_\mathrm{%s; %s}$' % (gdat.liststrgcomp[j], gdat.listlablinst[b][p]), '']
        if typemodl == 'pfss':
            for p in gdat.indxinst[1]:
                                ['', 'host_vsini,%g,1,uniform %g %g,$v \sin i$$,\n' % (gdat.vsiistar, 0, \
                                                                                                                            10 * gdat.vsiistar)], \
                                ['', 'host_lambda_%s,%g,1,uniform %g %g,$v \sin i$$,\n' % (gdat.liststrginst[1][p], gdat.lambstarprio, 0, \
                                                                                                                            10 * gdat.lambstarprio)], \
        
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                strgldc1 = 'host_ldc_q1_%s' % gdat.liststrginst[b][p]
                strgldc2 = 'host_ldc_q2_%s' % gdat.liststrginst[b][p]
                strgscal = 'ln_err_flux_%s' % gdat.liststrginst[b][p]
                strgbaseoffs = 'baseline_offset_flux_%s' % gdat.liststrginst[b][p]
                strggprosigm = 'baseline_gp_matern32_lnsigma_flux_%s' % gdat.liststrginst[b][p]
                strggprorhoo = 'baseline_gp_matern32_lnrho_flux_%s' % gdat.liststrginst[b][p]
                dictalleparadefa[strgldc1] = ['0.5', '1', 'uniform 0 1', '$q_{1; \mathrm{%s}}$' % gdat.listlablinst[b][p], '']
                dictalleparadefa[strgldc2] = ['0.5', '1', 'uniform 0 1', '$q_{2; \mathrm{%s}}$' % gdat.listlablinst[b][p], '']
                dictalleparadefa[strgscal] = ['-7', '1', 'uniform -10 -4', '$\ln{\sigma_\mathrm{%s}}$' % gdat.listlablinst[b][p], '']
                dictalleparadefa[strgbaseoffs] = ['0', '1', 'uniform -1 1', '$O_{\mathrm{%s}}$' % gdat.listlablinst[b][p], '']
                if b == 1:
                    dictalleparadefa['ln_jitter_rv_%s' % gdat.liststrginst[b][p]] = ['-10', '1', 'uniform -20 20', \
                                                                            '$\ln{\sigma_{\mathrm{RV;%s}}}$' % gdat.listlablinst[b][p], '']
                #lineadde.extend([ \
                #            ['', '%s,%f,1,uniform %f %f,$\ln{\sigma_{GP;\mathrm{TESS}}}$,\n' % \
                #                 (strggprosigm, -6, -12, 12)], \
                #            ['', '%s,%f,1,uniform %f %f,$\ln{\\rho_{GP;\mathrm{TESS}}}$,\n' % \
                #                 (strggprorhoo, -2, -12, 12)], \
                #           ])
                
        writ_filealle(gdat, 'params.csv', gdat.pathalle[typemodl], gdat.dictdictallepara[typemodl], dictalleparadefa)
    
    ## settings
    dictallesettdefa = dict()
    if typemodl == 'pfss':
        for j in gmod.indxcomp:
            dictallesettdefa['%s_flux_weighted_PFS' % gdat.liststrgcomp[j]] = 'True'
    
    pathsett = gdat.pathalle[typemodl] + 'settings.csv'
    if not os.path.exists(pathsett):
        cmnd = 'touch %s' % (pathsett)
        print(cmnd)
        os.system(cmnd)
        
        dictallesettdefa['fast_fit_width'] = '%.3g' % np.amax(gdat.duramask) / 24.
        dictallesettdefa['multiprocess'] = 'True'
        dictallesettdefa['multiprocess_cores'] = 'all'

        dictallesettdefa['mcmc_nwalkers'] = '100'
        dictallesettdefa['mcmc_total_steps'] = '100'
        dictallesettdefa['mcmc_burn_steps'] = '10'
        dictallesettdefa['mcmc_thin_by'] = '5'
        
        for p in gdat.indxinst[0]:
            dictallesettdefa['inst_phot'] = '%s' % gdat.liststrginst[0][p]
        
        for b in gdat.indxdatatser:
            if b == 0:
                strg = 'phot'
            if b == 1:
                strg = 'rv'
            for p in gdat.indxinst[b]:
                dictallesettdefa['inst_%s' % strg] = '%s' % gdat.liststrginst[b][p]
                dictallesettdefa['host_ld_law_%s' % gdat.liststrginst[b][p]] = 'quad'
                dictallesettdefa['host_grid_%s' % gdat.liststrginst[b][p]] = 'very_sparse'
                dictallesettdefa['baseline_flux_%s' % gdat.liststrginst[b][p]] = 'sample_offset'
        
        #dictallesettdefa['use_host_density_prior'] = 'False'
        
        if typemodl == '0003' or typemodl == '0004':
            dictallesettdefa['phase_curve'] = 'True'
            dictallesettdefa['phase_curve_style'] = 'sine_physical'
        
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                for j in gmod.indxcomp:
                    dictallesettdefa['%s_grid_%s' % (gdat.liststrgcomp[j], gdat.liststrginst[b][p])] = 'very_sparse'
            
            if gdat.numbinst[b] > 0:
                if b == 0:
                    strg = 'companions_phot'
                if b == 1:
                    strg = 'companions_rv'
                varb = ''
                cntr = 0
                for j in gmod.indxcomp:
                    if cntr != 0:
                        varb += ' '
                    varb += '%s' % gdat.liststrgcomp[j]
                    cntr += 1
                dictallesettdefa[strg] = varb
        
        dictallesettdefa['fast_fit'] = 'True'

        writ_filealle(gdat, 'settings.csv', gdat.pathalle[typemodl], gdat.dictdictallesett[typemodl], dictallesettdefa)
    
    ## initial plot
    path = gdat.pathalle[typemodl] + 'results/initial_guess_b.pdf'
    if not os.path.exists(path):
        allesfitter.show_initial_guess(gdat.pathalle[typemodl])
    
    ## do the run
    path = gdat.pathalle[typemodl] + 'results/mcmc_save.h5'
    if not os.path.exists(path):
        allesfitter.mcmc_fit(gdat.pathalle[typemodl])
    else:
        print('%s exists... Skipping the orbit run.' % path)

    ## make the final plots
    path = gdat.pathalle[typemodl] + 'results/mcmc_corner.pdf'
    if not os.path.exists(path):
        allesfitter.mcmc_output(gdat.pathalle[typemodl])
        
    # read the allesfitter posterior
    if gdat.typeverb > 0:
        print('Reading from %s...' % gdat.pathalle[typemodl])
    gdat.objtalle[typemodl] = allesfitter.allesclass(gdat.pathalle[typemodl])
    
    gdat.numbsampalle = allesfitter.config.BASEMENT.settings['mcmc_total_steps']
    gdat.numbwalkalle = allesfitter.config.BASEMENT.settings['mcmc_nwalkers']
    gdat.numbsampalleburn = allesfitter.config.BASEMENT.settings['mcmc_burn_steps']
    gdat.numbsampallethin = allesfitter.config.BASEMENT.settings['mcmc_thin_by']

    print('gdat.numbwalkalle')
    print(gdat.numbwalkalle)
    print('gdat.numbsampalle')
    print(gdat.numbsampalle)
    print('gdat.numbsampalleburn')
    print(gdat.numbsampalleburn)
    print('gdat.numbsampallethin')
    print(gdat.numbsampallethin)

    gdat.numbsamp = gdat.objtalle[typemodl].posterior_params[list(gdat.objtalle[typemodl].posterior_params.keys())[0]].size
    
    print('gdat.numbsamp')
    print(gdat.numbsamp)

    # temp 
    if gdat.numbsamp > 10000:
        gdat.indxsamp = np.random.choice(np.arange(gdat.numbsamp), size=10000, replace=False)
        gdat.numbsamp = 10000
    else:
        gdat.indxsamp = np.arange(gdat.numbsamp)
    
    print('gdat.numbsamp')
    print(gdat.numbsamp)
    
    calc_feat(gdat, typemodl)

    if gdat.boolsrchflar:
        gdat.arrytser['bdtrlowr'+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtrlowr'+typemodl] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.arrytser['bdtrmedi'+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtrmedi'+typemodl] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.arrytser['bdtruppr'+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtruppr'+typemodl] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.arrytser['bdtr'+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.arrytser['modl'+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.arrytser['resi'+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.listarrytser['bdtr'+typemodl] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.listarrytser['modl'+typemodl] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.listarrytser['resi'+typemodl] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
            gdat.arrytser['modl'+typemodl][b][p] = np.empty((gdat.time[b][p].size, 3))
            gdat.arrytser['modl'+typemodl][b][p][:, 0] = gdat.time[b][p]
            gdat.arrytser['modl'+typemodl][b][p][:, 1] = gdat.objtalle[typemodl].get_posterior_median_model(gdat.liststrginst[b][p], \
                                                                                                             gdat.liststrgtsercsvv[b], xx=gdat.time[b][p])
            gdat.arrytser['modl'+typemodl][b][p][:, 2] = 0.

            gdat.arrytser['resi'+typemodl][b][p] = np.copy(gdat.arrytser['bdtr'][b][p])
            gdat.arrytser['resi'+typemodl][b][p][:, 1] -= gdat.arrytser['modl'+typemodl][b][p][:, 1]
            for y in gdat.indxchun[b][p]:
                gdat.listarrytser['modl'+typemodl][b][p][y] = np.copy(gdat.listarrytser['bdtr'][b][p][y])
                gdat.listarrytser['modl'+typemodl][b][p][y][:, 1] = gdat.objtalle[typemodl].get_posterior_median_model(gdat.liststrginst[b][p], \
                                                                                                       gdat.liststrgtsercsvv[b], xx=gdat.listtime[b][p][y])
                
                gdat.listarrytser['resi'+typemodl][b][p][y] = np.copy(gdat.listarrytser['bdtr'][b][p][y])
                gdat.listarrytser['resi'+typemodl][b][p][y][:, 1] -= gdat.listarrytser['modl'+typemodl][b][p][y][:, 1]
    
                # plot residuals
                if gdat.boolplottser:
                    plot_tser(gdat, strgmodl, b, p, y, 'resi' + typemodl)

    # write the model to file
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
            path = gdat.pathdatatarg + 'arry%smodl_%s.csv' % (gdat.liststrgdatatser[b], gdat.liststrginst[b][p])
            if not os.path.exists(path):
                if gdat.typeverb > 0:
                    print('Writing to %s...' % path)
                np.savetxt(path, gdat.arrytser['modl'+typemodl][b][p], delimiter=',', \
                                                        header='time,%s,%s_err' % (gdat.liststrgtsercsvv[b], gdat.liststrgtsercsvv[b]))

    # number of samples to plot
    gdat.arrypcur['primbdtr'+typemodl] = [[[[] for j in gmod.indxcomp] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.arrypcur['primbdtr'+typemodl+'bindtotl'] = [[[[] for j in gmod.indxcomp] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.arrypcur['primbdtr'+typemodl+'bindzoom'] = [[[[] for j in gmod.indxcomp] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    
    gdat.listarrypcur = dict()
    gdat.listarrypcur['quadmodl'+typemodl] = [[[[] for j in gmod.indxcomp] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
            for j in gmod.indxcomp:
                gdat.listarrypcur['quadmodl'+typemodl][b][p][j] = np.empty((gdat.numbsampplot, gdat.numbtimeclen[b][p][j], 3))
    
    gdat.arrypcur['primbdtr'+typemodl] = [[[[] for j in gmod.indxcomp] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.arrypcur['primmodltotl'+typemodl] = [[[[] for j in gmod.indxcomp] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.arrytser['modlbase'+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    gdat.listarrytser['modlbase'+typemodl] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    
    gdat.listarrytsermodl = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
            gdat.listarrytsermodl[b][p] = np.empty((gdat.numbsampplot, gdat.numbtime[b][p], 3))
       
    for strgpcur in gdat.liststrgpcur:
        gdat.arrytser[strgpcur+typemodl] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                gdat.arrytser[strgpcur+typemodl][b][p] = np.copy(gdat.arrytser['bdtr'][b][p])
    for strgpcurcomp in gdat.liststrgpcurcomp:
        gdat.arrytser[strgpcurcomp+typemodl] = [[[[] for j in gmod.indxcomp] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                for j in gmod.indxcomp:
                    gdat.arrytser[strgpcurcomp+typemodl][b][p][j] = np.copy(gdat.arrytser['bdtr'][b][p])
    for strgpcurcomp in gdat.liststrgpcurcomp + gdat.liststrgpcur:
        for strgextnbins in ['', 'bindtotl']:
            gdat.arrypcur['quad' + strgpcurcomp + typemodl + strgextnbins] = [[[[] for j in gmod.indxcomp] \
                                                                                    for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
        
            gdat.listlcurmodl = np.empty((gdat.numbsampplot, gdat.time[b][p].size))
            print('Phase-folding the posterior samples from the model light curve...')
            for ii in tqdm(range(gdat.numbsampplot)):
                i = gdat.indxsampplot[ii]
                
                # this is only the physical model and excludes the baseline, which is available separately via get_one_posterior_baseline()
                gdat.listarrytsermodl[b][p][ii, :, 1] = gdat.objtalle[typemodl].get_one_posterior_model(gdat.liststrginst[b][p], \
                                                                        gdat.liststrgtsercsvv[b], xx=gdat.time[b][p], sample_id=i)
                
                for j in gmod.indxcomp:
                    gdat.listarrypcur['quadmodl'+typemodl][b][p][j][ii, :, :] = \
                                            ephesos.fold_tser(gdat.listarrytsermodl[b][p][ii, gdat.listindxtimeclen[j][b][p], :, :], \
                                                                                   gdat.dicterrr['epocmtracomp'][0, j], gdat.dicterrr['pericomp'][0, j], phasshft=0.25)
                    
            ## plot components in the zoomed panel
            for j in gmod.indxcomp:
                
                gdat.objtalle[typemodl] = allesfitter.allesclass(gdat.pathalle[typemodl])
                ### total model for this planet
                gdat.arrytser['modltotl'+typemodl][b][p][j][:, 1] = gdat.objtalle[typemodl].get_posterior_median_model(gdat.liststrginst[b][p], \
                                                                                                                                'flux', xx=gdat.time[b][p])
                
                ### stellar baseline
                gdat.objtalle[typemodl] = allesfitter.allesclass(gdat.pathalle[typemodl])
                gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_beaming_TESS'] = 0
                gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_ellipsoidal_TESS'] = 0
                if typemodl == '0003':
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_TESS'] = 0
                if typemodl == '0004':
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_thermal_TESS'] = 0
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_reflected_TESS'] = 0
                gdat.objtalle[typemodl].posterior_params_median['b_sbratio_TESS'] = 0
                gdat.arrytser['modlstel'+typemodl][b][p][j][:, 1] = gdat.objtalle[typemodl].get_posterior_median_model(gdat.liststrginst[b][p], \
                                                                                                                                'flux', xx=gdat.time[b][p])
                
                ### EV
                gdat.objtalle[typemodl] = allesfitter.allesclass(gdat.pathalle[typemodl])
                gdat.objtalle[typemodl].posterior_params_median['b_sbratio_TESS'] = 0
                gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_beaming_TESS'] = 0
                if typemodl == '0003':
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_TESS'] = 0
                if typemodl == '0004':
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_thermal_TESS'] = 0
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_reflected_TESS'] = 0
                gdat.arrytser['modlelli'+typemodl][b][p][j][:, 1] = gdat.objtalle[typemodl].get_posterior_median_model(gdat.liststrginst[b][p], \
                                                                                                                            'flux', xx=gdat.time[b][p])
                gdat.arrytser['modlelli'+typemodl][b][p][j][:, 1] -= gdat.arrytser['modlstel'+typemodl][b][p][j][:, 1]
                
                ### beaming
                gdat.objtalle[typemodl] = allesfitter.allesclass(gdat.pathalle[typemodl])
                gdat.objtalle[typemodl].posterior_params_median['b_sbratio_TESS'] = 0
                gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_ellipsoidal_TESS'] = 0
                if typemodl == '0003':
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_TESS'] = 0
                if typemodl == '0004':
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_thermal_TESS'] = 0
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_reflected_TESS'] = 0
                gdat.arrytser['modlbeam'+typemodl][b][p][j][:, 1] = gdat.objtalle[typemodl].get_posterior_median_model(gdat.liststrginst[b][p], \
                                                                                                                            'flux', xx=gdat.time[b][p])
                gdat.arrytser['modlbeam'+typemodl][b][p][j][:, 1] -= gdat.arrytser['modlstel'+typemodl][b][p][j][:, 1]
                
                # planetary
                gdat.arrytser['modlplan'+typemodl][b][p][j][:, 1] = gdat.arrytser['modltotl'+typemodl][b][p][j][:, 1] \
                                                                      - gdat.arrytser['modlstel'+typemodl][b][p][j][:, 1] \
                                                                      - gdat.arrytser['modlelli'+typemodl][b][p][j][:, 1] \
                                                                      - gdat.arrytser['modlbeam'+typemodl][b][p][j][:, 1]
                
                offsdays = np.mean(gdat.arrytser['modlplan'+typemodl][b][p][j][gdat.listindxtimetran[j][b][p][1], 1])
                gdat.arrytser['modlplan'+typemodl][b][p][j][:, 1] -= offsdays

                # planetary nightside
                gdat.objtalle[typemodl] = allesfitter.allesclass(gdat.pathalle[typemodl])
                gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_beaming_TESS'] = 0
                gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_ellipsoidal_TESS'] = 0
                if typemodl == '0003':
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_TESS'] = 0
                else:
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_thermal_TESS'] = 0
                    gdat.objtalle[typemodl].posterior_params_median['b_phase_curve_atmospheric_reflected_TESS'] = 0
                gdat.arrytser['modlnigh'+typemodl][b][p][j][:, 1] = gdat.objtalle[typemodl].get_posterior_median_model(gdat.liststrginst[b][p], \
                                                                                                                            'flux', xx=gdat.time[b][p])
                gdat.arrytser['modlnigh'+typemodl][b][p][j][:, 1] += gdat.dicterrr['amplnigh'][0, 0]
                gdat.arrytser['modlnigh'+typemodl][b][p][j][:, 1] -= gdat.arrytser['modlstel'+typemodl][b][p][j][:, 1]
                
                ### planetary modulation
                gdat.arrytser['modlpmod'+typemodl][b][p][j][:, 1] = gdat.arrytser['modlplan'+typemodl][b][p][j][:, 1] - \
                                                                                    gdat.arrytser['modlnigh'+typemodl][b][p][j][:, 1]
                    
                ### planetary residual
                gdat.arrytser['bdtrplan'+typemodl][b][p][j][:, 1] = gdat.arrytser['bdtr'][b][p][:, 1] \
                                                                                - gdat.arrytser['modlstel'+typemodl][b][p][j][:, 1] \
                                                                                - gdat.arrytser['modlelli'+typemodl][b][p][j][:, 1] \
                                                                                - gdat.arrytser['modlbeam'+typemodl][b][p][j][:, 1]
                gdat.arrytser['bdtrplan'+typemodl][b][p][j][:, 1] -= offsdays
                    
            # get allesfitter baseline model
            gdat.arrytser['modlbase'+typemodl][b][p] = np.copy(gdat.arrytser['bdtr'][b][p])
            gdat.arrytser['modlbase'+typemodl][b][p][:, 1] = gdat.objtalle[typemodl].get_posterior_median_baseline(gdat.liststrginst[b][p], 'flux', \
                                                                                                                                xx=gdat.time[b][p])
            # get allesfitter-detrended data
            gdat.arrytser['bdtr'+typemodl][b][p] = np.copy(gdat.arrytser['bdtr'][b][p])
            gdat.arrytser['bdtr'+typemodl][b][p][:, 1] = gdat.arrytser['bdtr'][b][p][:, 1] - gdat.arrytser['modlbase'+typemodl][b][p][:, 1]
            for y in gdat.indxchun[b][p]:
                # get allesfitter baseline model
                gdat.listarrytser['modlbase'+typemodl][b][p][y] = np.copy(gdat.listarrytser['bdtr'][b][p][y])
                gdat.listarrytser['modlbase'+typemodl][b][p][y][:, 1] = gdat.objtalle[typemodl].get_posterior_median_baseline(gdat.liststrginst[b][p], \
                                                                                           'flux', xx=gdat.listarrytser['modlbase'+typemodl][b][p][y][:, 0])
                # get allesfitter-detrended data
                gdat.listarrytser['bdtr'+typemodl][b][p][y] = np.copy(gdat.listarrytser['bdtr'][b][p][y])
                gdat.listarrytser['bdtr'+typemodl][b][p][y][:, 1] = gdat.listarrytser['bdtr'+typemodl][b][p][y][:, 1] - \
                                                                                gdat.listarrytser['modlbase'+typemodl][b][p][y][:, 1]
           
            print('Phase folding and binning the light curve for inference named %s...' % typemodl)
            for j in gmod.indxcomp:
                
                gdat.arrypcur['primmodltotl'+typemodl][b][p][j] = ephesos.fold_tser(gdat.arrytser['modltotl'+typemodl][b][p][j][gdat.listindxtimeclen[j][b][p], :, :], \
                                                                                    gdat.dicterrr['epocmtracomp'][0, j], gdat.dicterrr['pericomp'][0, j])
                
                gdat.arrypcur['primbdtr'+typemodl][b][p][j] = ephesos.fold_tser(gdat.arrytser['bdtr'+typemodl][b][p][gdat.listindxtimeclen[j][b][p], :, :], \
                                                                                    gdat.dicterrr['epocmtracomp'][0, j], gdat.dicterrr['pericomp'][0, j])
                
                gdat.arrypcur['primbdtr'+typemodl+'bindtotl'][b][p][j] = ephesos.rebn_tser(gdat.arrypcur['primbdtr'+typemodl][b][p][j], \
                                                                                                                    binsxdat=gdat.binsphasprimtotl)
                
                gdat.arrypcur['primbdtr'+typemodl+'bindzoom'][b][p][j] = ephesos.rebn_tser(gdat.arrypcur['primbdtr'+typemodl][b][p][j], \
                                                                                                                    binsxdat=gdat.binsphasprimzoom[j])

                for strgpcurcomp in gdat.liststrgpcurcomp + gdat.liststrgpcur:
                    
                    arrytsertemp = gdat.arrytser[strgpcurcomp+typemodl][b][p][gdat.listindxtimeclen[j][b][p], :, :]
                    
                    if strgpcurcomp == 'bdtr':
                        boolpost = True
                    else:
                        boolpost = False
                    gdat.arrypcur['quad'+strgpcurcomp+typemodl][b][p][j] = \
                                        ephesos.fold_tser(arrytsertemp, gdat.dicterrr['epocmtracomp'][0, j], gdat.dicterrr['pericomp'][0, j], phasshft=0.25) 
                
                    gdat.arrypcur['quad'+strgpcurcomp+typemodl+'bindtotl'][b][p][j] = ephesos.rebn_tser(gdat.arrypcur['quad'+strgpcurcomp+typemodl][b][p][j], \
                                                                                                                binsxdat=gdat.binsphasquadtotl)
                    
                    # write
                    path = gdat.pathdatatarg + 'arrypcurquad%sbindtotl_%s_%s.csv' % (strgpcurcomp, gdat.liststrgcomp[j], gdat.liststrginst[b][p])
                    if not os.path.exists(path):
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        np.savetxt(path, gdat.arrypcur['quad%s%sbindtotl' % (strgpcurcomp, typemodl)][b][p][j], delimiter=',', \
                                                        header='phase,%s,%s_err' % (gdat.liststrgtsercsvv[b], gdat.liststrgtsercsvv[b]))
                    
                    if gdat.boolplot:
                        plot_pser(gdat, strgmodl, 'quad'+strgpcurcomp+typemodl, boolpost=boolpost)
                
                
    # plots
    ## plot GP-detrended phase curves
    if gdat.boolplottser:
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                for y in gdat.indxchun[b][p]:
                    plot_tser(gdat, strgmodl, b, p, y, 'bdtr'+typemodl)
        plot_pser(gdat, strgmodl, 'primbdtr'+typemodl, boolpost=True)
    if gdat.boolplotpopl:
        plot_popl(gdat, gdat.typepriocomp + typemodl)
    
    # print out transit times
    for j in gmod.indxcomp:
        print(gdat.liststrgcomp[j])
        time = np.empty(500)
        for n in range(500):
            time[n] = gdat.dicterrr['epocmtracomp'][0, j] + gdat.dicterrr['pericomp'][0, j] * n
        objttime = astropy.time.Time(time, format='jd', scale='utc')#, out_subfmt='date_hm')
        listtimelabl = objttime.iso
        for n in range(500):
            if time[n] > 2458788 and time[n] < 2458788 + 200:
                print('%f, %s' % (time[n], listtimelabl[n]))


    if typemodl == '0003' or typemodl == '0004':
            
        if typemodl == '0003':
            gmod.listlablpara = [['Nightside', 'ppm'], ['Secondary', 'ppm'], ['Planetary Modulation', 'ppm'], ['Thermal', 'ppm'], \
                                                        ['Reflected', 'ppm'], ['Phase shift', 'deg'], ['Geometric Albedo', '']]
        else:
            gmod.listlablpara = [['Nightside', 'ppm'], ['Secondary', 'ppm'], ['Thermal', 'ppm'], \
                                  ['Reflected', 'ppm'], ['Thermal Phase shift', 'deg'], ['Reflected Phase shift', 'deg'], ['Geometric Albedo', '']]
        numbpara = len(gmod.listlablpara)
        indxpara = np.arange(numbpara)
        listpost = np.empty((gdat.numbsamp, numbpara))
        
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                for j in gmod.indxcomp:
                    listpost[:, 0] = gdat.dictlist['amplnigh'][:, j] * 1e6 # [ppm]
                    listpost[:, 1] = gdat.dictlist['amplseco'][:, j] * 1e6 # [ppm]
                    if typemodl == '0003':
                        listpost[:, 2] = gdat.dictlist['amplplan'][:, j] * 1e6 # [ppm]
                        listpost[:, 3] = gdat.dictlist['amplplanther'][:, j] * 1e6 # [ppm]
                        listpost[:, 4] = gdat.dictlist['amplplanrefl'][:, j] * 1e6 # [ppm]
                        listpost[:, 5] = gdat.dictlist['phasshftplan'][:, j]
                        listpost[:, 6] = gdat.dictlist['albg'][:, j]
                    else:
                        listpost[:, 2] = gdat.dictlist['amplplanther'][:, j] * 1e6 # [ppm]
                        listpost[:, 3] = gdat.dictlist['amplplanrefl'][:, j] * 1e6 # [ppm]
                        listpost[:, 4] = gdat.dictlist['phasshftplanther'][:, j]
                        listpost[:, 5] = gdat.dictlist['phasshftplanrefl'][:, j]
                        listpost[:, 6] = gdat.dictlist['albg'][:, j]
                    tdpy.plot_grid(gdat.pathalle[typemodl], 'pcur_%s' % typemodl, listpost, gmod.listlablpara, plotsize=2.5)

        # plot phase curve
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                
                ## determine data gaps for overplotting model without the data gaps
                gdat.indxtimegapp = np.argmax(gdat.time[b][p][1:] - gdat.time[b][p][:-1]) + 1
                
                for j in gmod.indxcomp:
                    path = gdat.pathalle[typemodl] + 'pcur_grid_%s_%s_%s.%s' % (typemodl, gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+2].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                    if not os.path.exists(path):
                        figr = plt.figure(figsize=(10, 12))
                        axis = [[] for k in range(3)]
                        axis[0] = figr.add_subplot(3, 1, 1)
                        axis[1] = figr.add_subplot(3, 1, 2)
                        axis[2] = figr.add_subplot(3, 1, 3, sharex=axis[1])
                        
                        for k in range(len(axis)):
                            
                            ## unbinned data
                            if k < 2:
                                if k == 0:
                                    xdat = gdat.time[b][p] - gdat.timeoffs
                                    ydat = gdat.arrytser['bdtr'+typemodl][b][p][:, 1] + gdat.dicterrr['amplnigh'][0, 0]
                                if k == 1:
                                    xdat = gdat.arrypcur['quadbdtr'+typemodl][b][p][j][:, 0]
                                    ydat = gdat.arrypcur['quadbdtr'+typemodl][b][p][j][:, 1] + gdat.dicterrr['amplnigh'][0, 0]
                                axis[k].plot(xdat, ydat, '.', color='grey', alpha=0.3, label='Raw data')
                            
                            ## binned data
                            if k > 0:
                                xdat = gdat.arrypcur['quadbdtr'+typemodl+'bindtotl'][b][p][j][:, 0]
                                ydat = gdat.arrypcur['quadbdtr'+typemodl+'bindtotl'][b][p][j][:, 1] + gdat.dicterrr['amplnigh'][0, 0]
                                yerr = np.copy(gdat.arrypcur['quadbdtr'+typemodl+'bindtotl'][b][p][j][:, 2])
                            else:
                                xdat = None
                                ydat = None
                                yerr = None
                            if k == 2:
                                ydat = (ydat - 1) * 1e6
                                yerr *= 1e6
                            # temp - add offset to bring the base of secondary to 0 
                            axis[k].errorbar(xdat, ydat, marker='o', yerr=yerr, capsize=0, ls='', color='k', label='Binned data')
                            
                            ## model
                            if k > 0:
                                xdat = gdat.arrypcur['quadmodl'+typemodl][b][p][j][:, 0]
                                ydat = gdat.arrypcur['quadmodl'+typemodl][b][p][j][:, 1] + gdat.dicterrr['amplnigh'][0, 0]
                            else:
                                xdat = gdat.arrytser['modltotl'+typemodl][b][p][j][:, 0] - gdat.timeoffs
                                ydat = gdat.arrytser['modltotl'+typemodl][b][p][j][:, 1] + gdat.dicterrr['amplnigh'][0, 0]
                            if k == 2:
                                ydat = (ydat - 1) * 1e6
                            if k == 0:
                                axis[k].plot(xdat[:gdat.indxtimegapp], ydat[:gdat.indxtimegapp], color='b', lw=2, label='Total Model', zorder=10)
                                axis[k].plot(xdat[gdat.indxtimegapp:], ydat[gdat.indxtimegapp:], color='b', lw=2, zorder=10)
                            else:
                                axis[k].plot(xdat, ydat, color='b', lw=2, label='Model', zorder=10)
                            
                            # add Vivien's result
                            if k == 2 and gdat.labltarg == 'WASP-121':
                                axis[k].plot(gdat.phasvivi, gdat.deptvivi*1e3, color='orange', lw=2, label='GCM (Parmentier+2018)')
                                axis[k].axhline(0., ls='-.', alpha=0.3, color='grey')

                            if k == 0:
                                axis[k].set(xlabel='Time [BJD - %d]' % gdat.timeoffs)
                            if k > 0:
                                axis[k].set(xlabel='Phase')
                        axis[0].set(ylabel=gdat.labltserphot)
                        axis[1].set(ylabel=gdat.labltserphot)
                        axis[2].set(ylabel='Relative flux - 1 [ppm]')
                        
                        if gdat.labltarg == 'WASP-121':
                            ylimpcur = [-400, 1000]
                        else:
                            ylimpcur = [-100, 300]
                        axis[2].set_ylim(ylimpcur)
                        
                        xdat = gdat.arrypcur['quadmodlstel'+typemodl][b][p][j][:, 0]
                        ydat = (gdat.arrypcur['quadmodlstel'+typemodl][b][p][j][:, 1] - 1.) * 1e6
                        axis[2].plot(xdat, ydat, lw=2, color='orange', label='Stellar baseline', ls='--', zorder=11)
                        
                        xdat = gdat.arrypcur['quadmodlelli'+typemodl][b][p][j][:, 0]
                        ydat = (gdat.arrypcur['quadmodlelli'+typemodl][b][p][j][:, 1] - 1.) * 1e6
                        axis[2].plot(xdat, ydat, lw=2, color='r', ls='--', label='Ellipsoidal variation')
                        
                        xdat = gdat.arrypcur['quadmodlelli'+typemodl][b][p][j][:, 0]
                        ydat = (gdat.arrypcur['quadmodlelli'+typemodl][b][p][j][:, 1] - 1.) * 1e6
                        axis[2].plot(xdat, ydat, lw=2, color='r', ls='--', label='Ellipsoidal variation')
                        
                        xdat = gdat.arrypcur['quadmodlplan'+typemodl][b][p][j][:, 0]
                        ydat = (gdat.arrypcur['quadmodlplan'+typemodl][b][p][j][:, 1] - 1.) * 1e6
                        axis[2].plot(xdat, ydat, lw=2, color='g', label='Planetary', ls='--')
    
                        xdat = gdat.arrypcur['quadmodlnigh'+typemodl][b][p][j][:, 0]
                        ydat = (gdat.arrypcur['quadmodlnigh'+typemodl][b][p][j][:, 1] - 1.) * 1e6
                        axis[2].plot(xdat, ydat, lw=2, color='olive', label='Planetary baseline', ls='--', zorder=11)
    
                        xdat = gdat.arrypcur['quadmodlpmod'+typemodl][b][p][j][:, 0]
                        ydat = (gdat.arrypcur['quadmodlpmod'+typemodl][b][p][j][:, 1] - 1.) * 1e6
                        axis[2].plot(xdat, ydat, lw=2, color='m', label='Planetary modulation', ls='--', zorder=11)
                         
                        ## legend
                        axis[2].legend(ncol=3)
                        
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        plt.savefig(path)
                        plt.close()
                   

        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                for j in gmod.indxcomp:
        
                    path = gdat.pathalle[typemodl] + 'pcur_samp_%s_%s_%s.%s' % (typemodl, gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    if not os.path.exists(path):
                        # replot phase curve
                        ### sample model phas
                        #numbphasfine = 1000
                        #gdat.meanphasfine = np.linspace(np.amin(gdat.arrypcur['quadbdtr'][0][gdat.indxphasotpr, 0]), \
                        #                                np.amax(gdat.arrypcur['quadbdtr'][0][gdat.indxphasotpr, 0]), numbphasfine)
                        #indxphasfineinse = np.where(abs(gdat.meanphasfine - 0.5) < phasseco)[0]
                        #indxphasfineotprleft = np.where(-gdat.meanphasfine > phasmask)[0]
                        #indxphasfineotprrght = np.where(gdat.meanphasfine > phasmask)[0]
       
                        indxphasmodlouttprim = [[] for a in range(2)]
                        indxphasdatabindouttprim = [[] for a in range(2)]
                        indxphasmodlouttprim[0] = np.where(gdat.arrypcur['quadmodl'+typemodl][b][p][j][:, 0] < -0.05)[0]
                        indxphasdatabindouttprim[0] = np.where(gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 0] < -0.05)[0]
                        indxphasmodlouttprim[1] = np.where(gdat.arrypcur['quadmodl'+typemodl][b][p][j][:, 0] > 0.05)[0]
                        indxphasdatabindouttprim[1] = np.where(gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 0] > 0.05)[0]

                    path = gdat.pathalle[typemodl] + 'pcur_comp_%s_%s_%s.%s' % (typemodl, gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+2].append({'path': path, 'limt':[0., 0.05, 0.5, 0.1]})
                    if not os.path.exists(path):
                        # plot the phase curve with components
                        figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
                        ## data
                        axis.errorbar(gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 0], \
                                       (gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 1] + gdat.dicterrr['amplnigh'][0, 0] - 1) * 1e6, \
                                       yerr=1e6*gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 2], color='k', marker='o', ls='', markersize=2, lw=1, label='Data')
                        ## total model
                        axis.plot(gdat.arrypcur['quadmodl'+typemodl][b][p][j][:, 0], \
                                                        1e6*(gdat.arrypcur['quadmodl'+typemodl][b][p][j][:, 1]+gdat.dicterrr['amplnigh'][0, 0]-1), \
                                                                                                                        color='b', lw=3, label='Model')
                        
                        axis.plot(gdat.arrypcur['quadmodlplan'+typemodl][b][p][j][:, 0], 1e6*(gdat.arrypcur['quadmodlplan'+typemodl][b][p][j][:, 1]), \
                                                                                                                      color='g', label='Planetary', lw=1, ls='--')
                        
                        axis.plot(gdat.arrypcur['quadmodlbeam'+typemodl][b][p][j][:, 0], 1e6*(gdat.arrypcur['quadmodlbeam'+typemodl][b][p][j][:, 1]), \
                                                                                                              color='m', label='Beaming', lw=2, ls='--')
                        
                        axis.plot(gdat.arrypcur['quadmodlelli'+typemodl][b][p][j][:, 0], 1e6*(gdat.arrypcur['quadmodlelli'+typemodl][b][p][j][:, 1]), \
                                                                                                              color='r', label='Ellipsoidal variation', lw=2, ls='--')
                        
                        axis.plot(gdat.arrypcur['quadmodlstel'+typemodl][b][p][j][:, 0], 1e6*(gdat.arrypcur['quadmodlstel'+typemodl][b][p][j][:, 1]-1.), \
                                                                                                              color='orange', label='Stellar baseline', lw=2, ls='--')
                        
                        axis.set_ylim(ylimpcur)
                        axis.set_ylabel('Relative flux [ppm]')
                        axis.set_xlabel('Phase')
                        axis.legend(ncol=3)
                        plt.tight_layout()
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        plt.savefig(path)
                        plt.close()

                    path = gdat.pathalle[typemodl] + 'pcur_samp_%s_%s_%s.%s' % (typemodl, gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+2].append({'path': path, 'limt':[0., 0.05, 0.5, 0.1]})
                    if not os.path.exists(path):
                        # plot the phase curve with samples
                        figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
                        axis.errorbar(gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 0], \
                                    (gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 1] + gdat.dicterrr['amplnigh'][0, 0] - 1) * 1e6, \
                                                     yerr=1e6*gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 2], color='k', marker='o', ls='', markersize=2, lw=1)
                        for ii, i in enumerate(gdat.indxsampplot):
                            axis.plot(gdat.arrypcur['quadmodl'+typemodl][b][p][j][:, 0], \
                                                        1e6 * (gdat.listarrypcur['quadmodl'+typemodl][b][p][j][ii, :] + gdat.dicterrr['amplnigh'][0, 0] - 1.), \
                                                                                                                                          alpha=0.1, color='b')
                        axis.set_ylabel('Relative flux [ppm]')
                        axis.set_xlabel('Phase')
                        axis.set_ylim(ylimpcur)
                        plt.tight_layout()
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        plt.savefig(path)
                        plt.close()

                    # plot all along with residuals
                    #path = gdat.pathalle[typemodl] + 'pcur_resi_%s_%s_%s.%s' % (typemodl, gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                    #if not os.path.exists(path):
                    #   figr, axis = plt.subplots(3, 1, figsize=gdat.figrsizeydob)
                    #   axis.errorbar(gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 0], (gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 1]) * 1e6, \
                    #                          yerr=1e6*gdat.arrypcur['quadbdtrbindtotl'][b][p][j][:, 2], color='k', marker='o', ls='', markersize=2, lw=1)
                    #   for kk, k in enumerate(gdat.indxsampplot):
                    #       axis.plot(gdat.meanphasfine[indxphasfineotprleft], (listmodltotl[k, indxphasfineotprleft] - listoffs[k]) * 1e6, \
                    #                                                                                                               alpha=0.1, color='b')
                    #       axis.plot(gdat.meanphasfine[indxphasfineotprrght], (listmodltotl[k, indxphasfineotprrght] - listoffs[k]) * 1e6, \
                    #                                                                                                               alpha=0.1, color='b')
                    #   axis.set_ylabel('Relative flux - 1 [ppm]')
                    #   axis.set_xlabel('Phase')
                    #   plt.tight_layout()
                    #   print('Writing to %s...' % path)
                    #   plt.savefig(path)
                    #   plt.close()

                    # write to text file
                    path = gdat.pathalle[typemodl] + 'post_pcur_%s_tabl.csv' % (typemodl)
                    if not os.path.exists(path):
                        fileoutp = open(gdat.pathalle[typemodl] + 'post_pcur_%s_tabl.csv' % (typemodl), 'w')
                        for strgfeat in gdat.dictlist:
                            if gdat.dictlist[strgfeat].ndim == 2:
                                for j in gmod.indxcomp:
                                    fileoutp.write('%s,%s,%g,%g,%g,%g,%g\\\\\n' % (strgfeat, gdat.liststrgcomp[j], gdat.dictlist[strgfeat][0, j], gdat.dictlist[strgfeat][1, j], \
                                                                                gdat.dictlist[strgfeat][2, j], gdat.dicterrr[strgfeat][1, j], gdat.dicterrr[strgfeat][2, j]))
                            else:
                                fileoutp.write('%s,,%g,%g,%g,%g,%g\\\\\n' % (strgfeat, gdat.dictlist[strgfeat][0], gdat.dictlist[strgfeat][1], \
                                                                                gdat.dictlist[strgfeat][2], gdat.dicterrr[strgfeat][1], gdat.dicterrr[strgfeat][2]))
                            #fileoutp.write('\\\\\n')
                        fileoutp.close()
                    
                    path = gdat.pathalle[typemodl] + 'post_pcur_%s_cmnd.csv' % (typemodl)
                    if not os.path.exists(path):
                        fileoutp = open(gdat.pathalle[typemodl] + 'post_pcur_%s_cmnd.csv' % (typemodl), 'w')
                        for strgfeat in gdat.dictlist:
                            if gdat.dictlist[strgfeat].ndim == 2:
                                for j in gmod.indxcomp:
                                    fileoutp.write('%s,%s,$%.3g \substack{+%.3g \\\\ -%.3g}$\\\\\n' % (strgfeat, gdat.liststrgcomp[j], gdat.dicterrr[strgfeat][0, j], \
                                                                                                gdat.dicterrr[strgfeat][1, j], gdat.dicterrr[strgfeat][2, j]))
                            else:
                                fileoutp.write('%s,,$%.3g \substack{+%.3g \\\\ -%.3g}$\\\\\n' % (strgfeat, gdat.dicterrr[strgfeat][0], \
                                                                                                            gdat.dicterrr[strgfeat][1], gdat.dicterrr[strgfeat][2]))
                            #fileoutp.write('\\\\\n')
                        fileoutp.close()

                if typemodl == '0003':
                    
                    # wavelength axis
                    gdat.conswlentmpt = 0.0143877735e6 # [um K]

                    minmalbg = min(np.amin(gdat.dictlist['albginfo']), np.amin(gdat.dictlist['albg']))
                    maxmalbg = max(np.amax(gdat.dictlist['albginfo']), np.amax(gdat.dictlist['albg']))
                    binsalbg = np.linspace(minmalbg, maxmalbg, 100)
                    meanalbg = (binsalbg[1:] + binsalbg[:-1]) / 2.
                    pdfnalbg = tdpy.retr_kdegpdfn(gdat.dictlist['albg'][:, 0], binsalbg, 0.02)
                    pdfnalbginfo = tdpy.retr_kdegpdfn(gdat.dictlist['albginfo'][:, 0], binsalbg, 0.02)
                    
                    path = gdat.pathalle[typemodl] + 'pdfn_albg_%s_%s.%s' % (gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                    if not os.path.exists(path):
                        figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
                        axis.plot(meanalbg, pdfnalbg, label='TESS only', lw=2)
                        axis.plot(meanalbg, pdfnalbginfo, label='TESS + ATMO', lw=2)
                        axis.set_xlabel('$A_g$')
                        axis.set_ylabel('$P(A_g)$')
                        axis.legend()
                        axis.set_xlim([0, None])
                        plt.subplots_adjust()
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        plt.savefig(path)
                        plt.close()
                
                    path = gdat.pathalle[typemodl] + 'hist_albg_%s_%s.%s' % (gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                    if not os.path.exists(path):
                        figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
                        axis.hist(gdat.dictlist['albg'][:, 0], label='TESS only', bins=binsalbg)
                        axis.hist(gdat.dictlist['albginfo'][:, 0], label='TESS + ATMO', bins=binsalbg)
                        axis.set_xlabel('$A_g$')
                        axis.set_ylabel('$N(A_g)$')
                        axis.legend()
                        plt.subplots_adjust()
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        plt.savefig(path)
                        plt.close()
                
                    #liststrgfile = ['ContribFuncArr.txt', \
                    #                'EmissionDataArray.txt', \
                    #                #'RetrievalParamSamples.txt', \
                    #                'ContribFuncWav.txt', \
                    #                'EmissionModelArray.txt', \
                    #                'RetrievalPTSamples.txt', \
                    #                'pdependent_abundances/', \
                    #                ]
                    
                    # get the ATMO posterior
                    path = gdat.pathdatatarg + 'ascii_output/RetrievalParamSamples.txt'
                    listsampatmo = np.loadtxt(path)
                    
                    # plot ATMO posterior
                    gmod.listlablpara = [['$\kappa_{IR}$', ''], ['$\gamma$', ''], ['$\psi$', ''], ['[M/H]', ''], \
                                                                                                    ['[C/H]', ''], ['[O/H]', '']]
                    tdpy.plot_grid(gdat.pathalle[typemodl], 'post_atmo', listsampatmo, gmod.listlablpara, plotsize=2.5)
   
                    # get the ATMO posterior on irradiation efficiency, psi
                    indxsampatmo = np.random.choice(np.arange(listsampatmo.shape[0]), size=gdat.numbsamp, replace=False)
                    gdat.listpsii = listsampatmo[indxsampatmo, 2]
                    
                    gdat.gmeatmptequi = np.percentile(gdat.dictlist['tmptequi'][:, 0], 50.)
                    gdat.gstdtmptequi = (np.percentile(gdat.dictlist['tmptequi'][:, 0], 84.) - np.percentile(gdat.dictlist['tmptequi'][:, 0], 16.)) / 2.
                    gdat.gmeatmptdayy = np.percentile(gdat.dictlist['tmptdayy'][:, 0], 50.)
                    gdat.gstdtmptdayy = (np.percentile(gdat.dictlist['tmptdayy'][:, 0], 84.) - np.percentile(gdat.dictlist['tmptdayy'][:, 0], 16.)) / 2.
                    gdat.gmeatmptnigh = np.percentile(gdat.dictlist['tmptnigh'][:, 0], 50.)
                    gdat.gstdtmptnigh = (np.percentile(gdat.dictlist['tmptnigh'][:, 0], 84.) - np.percentile(gdat.dictlist['tmptnigh'][:, 0], 16.)) / 2.
                    gdat.gmeapsii = np.percentile(gdat.listpsii, 50.)
                    gdat.gstdpsii = (np.percentile(gdat.listpsii, 84.) - np.percentile(gdat.listpsii, 16.)) / 2.
                
                    histpsii, gdat.binspsii = np.histogram(gdat.listpsii, 1001)
                    gdat.meanpsii = (gdat.binspsii[1:] + gdat.binspsii[:-1]) / 2.
                    
                    gdat.kdegstdvpsii = 0.01
                    path = gdat.pathalle[typemodl] + 'kdeg_psii_%s_%s.%s' % (gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                    if not os.path.exists(path):
                        figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
                        gdat.kdegpsii = tdpy.retr_kdeg(gdat.listpsii, gdat.meanpsii, gdat.kdegstdvpsii)
                        axis.plot(gdat.meanpsii, gdat.kdegpsii)
                        axis.set_xlabel('$\psi$')
                        axis.set_ylabel('$K_\psi$')
                        plt.subplots_adjust()
                        if gdat.typeverb > 0:
                            print('Writing to %s...' % path)
                        plt.savefig(path)
                        plt.close()
                
                    # use psi posterior to infer Bond albedo and heat circulation efficiency
                    numbsampwalk = 10000
                    numbsampburnwalk = 1000
                    gmod.listlablpara = [['$A_b$', ''], ['$E$', ''], [r'$\varepsilon$', '']]
                    listscalpara = ['self', 'self', 'self']
                    gmod.listminmpara = np.array([0., 0., 0.])
                    gmod.listmaxmpara = np.array([1., 1., 1.])
                    strgextn = 'albbepsi'
                    listpostheat = tdpy.samp(gdat, numbsampwalk, retr_llik_albbepsi, \
                                                  gmod.listlablpara, listscalpara, gmod.listminmpara, gmod.listmaxmpara, boolplot=gdat.boolplot, \
                                                  pathbase=gdat.pathtargruns, \
                                                  typeverb=gdat.typeverb, \
                                                  numbsampburnwalk=numbsampburnwalk, strgextn=strgextn)

                    # plot emission spectra, secondary eclipse depth, and brightness temperature
                    #listcolr = ['k', 'm', 'purple', 'olive', 'olive', 'r', 'g']
                    listcolr = ['k', 'm', 'purple', 'olive', 'olive', 'r', 'g']
                    for i in range(15):
                        listcolr.append('r')
                    for i in range(28):
                        listcolr.append('g')
                    figr, axis = plt.subplots(4, 1, figsize=(12, 12), sharex=True)
                    ## stellar emission spectrum and TESS throughput
                    axis[0].plot(arrymodl[:, 0], 1e-9 * arrymodl[:, 9], label='Host star', color='grey')
                    axis[0].plot(0., 0., ls='--', label='TESS Throughput', color='grey')
                    axis[0].set_ylabel(r'$\nu F_{\nu}$ [10$^9$ erg/s/cm$^2$]')
                    axis[0].legend(fancybox=True, bbox_to_anchor=[0.7, 0.22, 0.2, 0.2])
                    axistwin = axis[0].twinx()
                    axistwin.plot(gdat.meanwlenband, gdat.thptband, color='grey', ls='--', label='TESS')
                    axistwin.set_ylabel(r'Throughput')
                    
                    ## secondary eclipse depths
                    ### model
                    objtplotmodllavgd, = axis[1].plot(arrydata[0, 0], 1e6*gdat.amplplantheratmo, color='b', marker='D')
                    axis[1].plot(arrymodl[:, 0], arrymodl[:, 1], label='1D Retrieval (This work)', color='b')
                    axis[1].plot(arrymodl[:, 0], arrymodl[:, 2], label='Blackbody (This work)', alpha=0.3, color='deepskyblue')
                    axis[1].fill_between(arrymodl[:, 0], arrymodl[:, 3], arrymodl[:, 4], alpha=0.3, color='deepskyblue')
                    objtplotvivi, = axis[1].plot(gdat.wlenvivi, gdat.specvivi * 1e6, color='orange', alpha=0.6, lw=2)
                    ### data
                    for k in range(5):
                        axis[1].errorbar(arrydata[k, 0], arrydata[k, 2], xerr=arrydata[k, 1], yerr=arrydata[k, 3], ls='', marker='o', color=listcolr[k])
                    axis[1].errorbar(arrydata[5:22, 0], arrydata[5:22, 2], xerr=arrydata[5:22, 1], yerr=arrydata[5:22, 3], ls='', marker='o', color='r')
                    axis[1].errorbar(arrydata[22:-1, 0], arrydata[22:-1, 2], xerr=arrydata[22:-1, 1], yerr=arrydata[22:-1, 3], ls='', marker='o', color='g')
                    axis[1].set_ylabel(r'Depth [ppm]')
                    axis[1].set_xticklabels([])
                    
                    ## planetary emission spectra
                    ### model
                    objtplotretr, = axis[2].plot(arrymodl[:, 0], 1e-9 * arrymodl[:, 5], label='1D Retrieval (This work)', color='b')
                    objtplotmblc, = axis[2].plot(arrymodl[:, 0], 1e-9 * arrymodl[:, 6], label='Blackbody (This work)', color='deepskyblue', alpha=0.3)
                    objtploteblc = axis[2].fill_between(arrymodl[:, 0], 1e-9 * arrymodl[:, 7], 1e-9 * arrymodl[:, 8], color='deepskyblue', alpha=0.3)
                    axis[2].legend([objtplotretr, objtplotmodllavgd, (objtplotmblc, objtploteblc), objtplotvivi], \
                                               ['1D Retrieval (This work)', '1D Retrieval (This work), Avg', 'Blackbody (This work)', 'GCM (Parmentier+2018)'], \
                                                                                            bbox_to_anchor=[0.8, 1.4, 0.2, 0.2])
                    ### data
                    for k in range(5):
                        axis[2].errorbar(arrydata[k, 0],  1e-9 * arrydata[k, 6], xerr=arrydata[k, 1], yerr=1e-9*arrydata[k, 7], ls='', marker='o', color=listcolr[k])
                    axis[2].errorbar(arrydata[5:22, 0], 1e-9 * arrydata[5:22, 6], xerr=arrydata[5:22, 1], yerr=1e-9*arrydata[5:22, 7], ls='', marker='o', color='r')
                    axis[2].errorbar(arrydata[22:-1, 0], 1e-9 * arrydata[22:-1, 6], xerr=arrydata[22:-1, 1], \
                                                                    yerr=1e-9*arrydata[22:-1, 7], ls='', marker='o', color='g')
                    
                    axis[2].set_ylabel(r'$\nu F_{\nu}$ [10$^9$ erg/s/cm$^2$]')
                    axis[2].set_xticklabels([])
                    
                    ## brightness temperature
                    ### data
                    for k in range(5):
                        if k == 0:
                            labl = 'TESS (This work)'
                        if k == 1:
                            labl = 'Z$^\prime$ (Delrez+2016)'
                        if k == 2:
                            labl = '$K_s$ (Kovacs\&Kovacs2019)'
                        if k == 3:
                            labl = 'IRAC $\mu$m (Garhart+2019)'
                        #if k == 4:
                        #    labl = 'IRAC 4.5 $\mu$m (Garhart+2019)'
                        axis[3].errorbar(arrydata[k, 0], arrydata[k, 4], xerr=arrydata[k, 1], yerr=arrydata[k, 5], label=labl, ls='', marker='o', color=listcolr[k])
                    axis[3].errorbar(arrydata[5:22, 0], arrydata[5:22, 4], xerr=arrydata[5:22, 1], \
                                                         yerr=arrydata[5:22, 5], label='HST G102 (Evans+2019)', ls='', marker='o', color='r')
                    axis[3].errorbar(arrydata[22:-1, 0], arrydata[22:-1, 4], xerr=arrydata[22:-1, 1], \
                                                        yerr=arrydata[22:-1, 5], label='HST G141 (Evans+2017)', ls='', marker='o', color='g')
                    #axis[3].errorbar(arrydata[:, 0], np.median(tmpt, 0), xerr=arrydata[:, 1], yerr=np.std(tmpt, 0), label='My calc', ls='', marker='o', color='c')
                    axis[3].set_ylabel(r'$T_B$ [K]')
                    axis[3].set_xlabel(r'$\lambda$ [$\mu$m]')
                    axis[3].legend(fancybox=True, bbox_to_anchor=[0.8, 3.8, 0.2, 0.2], ncol=2)
                    
                    axis[1].set_ylim([20, None])
                    axis[1].set_yscale('log')
                    for i in range(4):
                        axis[i].set_xscale('log')
                    axis[3].set_xlim([0.5, 5])
                    axis[3].xaxis.set_minor_formatter(mpl.ticker.ScalarFormatter())
                    axis[3].xaxis.set_major_formatter(mpl.ticker.ScalarFormatter())
                    plt.subplots_adjust(hspace=0., wspace=0.)
                    path = gdat.pathalle[typemodl] + 'spec_%s_%s.%s' % (gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                    if gdat.typeverb > 0:
                        print('Writing to %s...' % path)
                    plt.savefig(path)
                    plt.close()
                    
                    # get contribution function
                    path = gdat.pathdatatarg + 'ascii_output/ContribFuncArr.txt'
                    if gdat.typeverb > 0:
                        print('Reading from %s...' % path)
                    ctrb = np.loadtxt(path)
                    presctrb = ctrb[0, :]
                    # interpolate the throughput
                    gdat.thptbandctrb = scipy.interpolate.interp1d(gdat.meanwlenband, gdat.thptband, fill_value=0, bounds_error=False)(wlenctrb)
                    numbwlenctrb = wlenctrb.size
                    indxwlenctrb = np.arange(numbwlenctrb)
                    numbpresctrb = presctrb.size
                    indxpresctrb = np.arange(numbpresctrb)

                    # plot pressure-temperature, contribution function, abundances
                    ## get ATMO posterior
                    path = gdat.pathdatatarg + 'ascii_output/RetrievalPTSamples.txt'
                    dataptem = np.loadtxt(path)
                    liststrgcomp = ['CH4.txt', 'CO.txt', 'FeH.txt', 'H+.txt', 'H.txt', 'H2.txt', 'H2O.txt', 'H_.txt', 'He.txt', 'K+.txt', \
                                                                        'K.txt', 'NH3.txt', 'Na+.txt', 'Na.txt', 'TiO.txt', 'VO.txt', 'e_.txt']
                    listlablcomp = ['CH$_4$', 'CO', 'FeH', 'H$^+$', 'H', 'H$_2$', 'H$_2$O', 'H$^-$', 'He', 'K$^+$', \
                                                                        'K', 'NH$_3$', 'Na$^+$', 'Na', 'TiO', 'VO', 'e$^-$']
                    listdatacomp = []
                    for strg in liststrgcomp:
                        path = gdat.pathdatatarg + 'ascii_output/pdependent_abundances/' + strg
                        listdatacomp.append(np.loadtxt(path))
                    ## plot
                    figr, axis = plt.subplots(nrows=1, ncols=2, sharey=True, gridspec_kw={'width_ratios': [1, 2]}, figsize=gdat.figrsizeydob)
                    ### pressure temperature
                    numbsamp = dataptem.shape[0] - 1
                    indxsamp = np.arange(numbsamp)
                    for i in indxsamp[::100]:
                        axis[0].plot(dataptem[i, :], dataptem[0, :], color='b', alpha=0.1)
                    axis[0].plot(np.percentile(dataptem, 10, axis=0), dataptem[0, :], color='g')
                    axis[0].plot(np.percentile(dataptem, 50, axis=0), dataptem[0, :], color='r')
                    axis[0].plot(np.percentile(dataptem, 90, axis=0), dataptem[0, :], color='g')
                    axis[0].set_xlim([1500, 3700])
                    axis[0].set_xlabel('$T$ [K]')
                    axis[0].set_yscale('log')
                    axis[0].set_ylabel('$P$ [bar]')
                    axis[0].invert_yaxis()
                    axis[0].set_ylim([10., 1e-5])
                    ### contribution function
                    axistwin = axis[0].twiny()
                    ctrbtess = np.empty(numbpresctrb)
                    for k in indxpresctrb:
                        ctrbtess[k] = np.sum(ctrb[1:, k] * gdat.thptbandctrb)
                    ctrbtess *= 1e-12 / np.amax(ctrbtess)
                    axistwin.fill(ctrbtess, presctrb, alpha=0.5, color='grey')
                    axistwin.set_xticklabels([])
                    ## abundances
                    numbcomp = len(listdatacomp)
                    indxcomp = np.arange(numbcomp)
                    listobjtcolr = sns.color_palette('hls', numbcomp)
                    axis[1].set_prop_cycle('color', listobjtcolr)
                    listcolr = []
                    for k in indxcomp:
                        objt, = axis[1].plot(listdatacomp[k][:, 1], listdatacomp[k][:, 0])
                        listcolr.append(objt.get_color())

                    axis[1].xaxis.tick_top()
                    
                    arry = np.logspace(-16., 0., 21) # x 0.8
                    for k in range(21):
                        axis[1].axvline(arry[k], ls='--', alpha=0.1, color='k')
                    arry = np.logspace(-5., 1., 11) # y 0.6
                    for k in range(11):
                        axis[1].axhline(arry[k], ls='--', alpha=0.1, color='k')
                    listobjtcolr = sns.color_palette('hls', numbcomp)
                    axis[1].set_prop_cycle('color', listobjtcolr)
                    for k in indxcomp:
                        if k == 0: # CH4
                            xpos, ypos = 10**-12.8, 10**-2.3
                        elif k == 1: # CO
                            xpos, ypos = 10**-2.8, 10**-3.5
                        elif k == 2: # FeH
                            xpos, ypos = 10**-10.8, 10**-3.5
                        elif k == 3: # H+
                            xpos, ypos = 10**-12.8, 10**-4.1
                        elif k == 4: # H
                            xpos, ypos = 10**-1.6, 10**-2
                        elif k == 5: # H2
                            xpos, ypos = 10**-1.6, 10**-2.6
                        elif k == 6: # H20
                            xpos, ypos = 10**-8.8, 10**-4.1
                        elif k == 7: # H_
                            xpos, ypos = 10**-10., 10**0.4
                        elif k == 8: # He
                            xpos, ypos = 10**-1.6, 10**-4.1
                        elif k == 9: # K+
                            xpos, ypos = 10**-4.4, 10**-4.8
                        elif k == 10: # K
                            xpos, ypos = 10**-8.4, 10**-4.8
                        elif k == 11: # Nh3
                            xpos, ypos = 10**-13.6, 10**-4.1
                        elif k == 12: # Na+
                            xpos, ypos = 10**-4.4, 10**-3.8
                        elif k == 13: # Na
                            xpos, ypos = 10**-6, 10**-3.8
                        elif k == 14: # TiO
                            xpos, ypos = 10**-7.6, 10**-2
                        elif k == 15: # VO
                            xpos, ypos = 10**-6, 10**-2
                        elif k == 16: # e-
                            xpos, ypos = 10**-5.6, 10**-0.8
                        else:
                            xpos = 10**(np.random.rand() * 16. - 16.)
                            ypos = 10**(np.random.rand() * 6. - 5.)
                        axis[1].text(xpos, ypos, '%s' % listlablcomp[k], color=listcolr[k], size=10, va='center', ha='center')
                    axis[1].set_xscale('log')
                    axis[1].set_xlabel('Volume Mixing Ratio')
                    axis[1].set_yscale('log')
                    axis[1].set_xlim([1e-16, 1])
                    plt.subplots_adjust(hspace=0., wspace=0., bottom=0.15)
                    path = gdat.pathalle[typemodl] + 'ptem_%s_%s.%s' % (gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
                    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                    if gdat.typeverb > 0:
                        print('Writing to %s...' % path)
                    plt.savefig(path)
                    plt.close()
  

def plot_popl(gdat, strgpdfn):
    
    print('Plotting target features along with population features for strgpdfn: %s' % strgpdfn)
        
    pathvisufeatplan = getattr(gdat, 'pathvisufeatplan' + strgpdfn)
    pathvisudataplan = getattr(gdat, 'pathvisudataplan' + strgpdfn)
    pathvisufeatsyst = getattr(gdat, 'pathvisufeatsyst' + strgpdfn)
    
    ## occurence rate as a function of planet radius with highlighted radii of the system's planets
    ### get the CKS occurence rate as a function of planet radius
    path = gdat.pathbasemile + 'data/Fulton+2017/Means.csv'
    data = np.loadtxt(path, delimiter=',')
    timeoccu = data[:, 0]
    occumean = data[:, 1]
    path = gdat.pathbasemile + 'data/Fulton+2017/Lower.csv'
    occulowr = np.loadtxt(path, delimiter=',')
    occulowr = occulowr[:, 1]
    path = gdat.pathbasemile + 'data/Fulton+2017/Upper.csv'
    occuuppr = np.loadtxt(path, delimiter=',')
    occuuppr = occuuppr[:, 1]
    occuyerr = np.empty((2, occumean.size))
    occuyerr[0, :] = occuuppr - occumean
    occuyerr[1, :] = occumean - occulowr
    
    figr, axis = plt.subplots(figsize=gdat.figrsize)
    
    # this system
    for jj, j in enumerate(gmod.indxcomp):
        if strgpdfn == 'post':
            xposlowr = gdat.dictpost['radicomp'][0, j]
            xposmedi = gdat.dictpost['radicomp'][1, j]
            xposuppr = gdat.dictpost['radicomp'][2, j]
        else:
            xposmedi = gdat.rratcompprio[j] * gdat.radistar
            xposlowr = xposmedi - gdat.stdvrratcompprio[j] * gdat.radistar
            xposuppr = xposmedi + gdat.stdvrratcompprio[j] * gdat.radistar
        xposlowr *= gdat.dictfact['rjre']
        xposuppr *= gdat.dictfact['rjre']
        axis.axvspan(xposlowr, xposuppr, alpha=0.5, color=gdat.listcolrcomp[j])
        axis.axvline(xposmedi, color=gdat.listcolrcomp[j], ls='--', label=gdat.liststrgcomp[j])
        axis.text(0.7, 0.9 - jj * 0.07, r'\textbf{%s}' % gdat.liststrgcomp[j], color=gdat.listcolrcomp[j], \
                                                                                    va='center', ha='center', transform=axis.transAxes)
    xerr = (timeoccu[1:] - timeoccu[:-1]) / 2.
    xerr = np.concatenate([xerr[0, None], xerr])
    axis.errorbar(timeoccu, occumean, yerr=occuyerr, xerr=xerr, color='black', ls='', marker='o', lw=1, zorder=10)
    axis.set_xlabel('Radius [$R_E$]')
    axis.set_ylabel('Occurrence rate of planets per star')
    plt.subplots_adjust(bottom=0.2)
    plt.subplots_adjust(left=0.2)
    path = pathvisufeatplan + 'occuradi_%s_%s.%s' % (gdat.strgtarg, strgpdfn, gdat.typefileplot)
    #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
    print('Writing to %s...' % path)
    plt.savefig(path)
    plt.close()
  
    # visualize the system
    path = pathvisufeatplan + 'orbt_%s_%s' % (gdat.strgtarg, strgpdfn)
    path = gdat.pathvisutarg + 'orbt'
    listtypevisu = ['real', 'cart']
    
    for typevisu in listtypevisu:
        
        if strgpdfn == 'post':
            radicomp = gdat.dicterrr['radicomp'][0, :]
            rsmacomp = gdat.dicterrr['rsmacomp'][0, :]
            epocmtracomp = gdat.dicterrr['epocmtracomp'][0, :]
            pericomp = gdat.dicterrr['pericomp'][0, :]
            cosicomp = gdat.dicterrr['cosicomp'][0, :]
        else:
            radicomp = gdat.radicompprio
            rsmacomp = gdat.rsmacompprio
            epocmtracomp = gdat.epocmtracompprio
            pericomp = gdat.pericompprio
            cosicomp = gdat.cosicompprio

        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                dictoutp = ephesos.eval_modl( \
                                             gdat.arrytser['bdtr'][b][p][:, 0, 0], \
                                             
                                             radicomp=radicomp, \
                                             rsmacomp=rsmacomp, \
                                             epocmtracomp=epocmtracomp, \
                                             pericomp=pericomp, \
                                             cosicomp=cosicomp, \

                                             typelmdk='quad', \
                                             
                                             typesyst=gdat.fitt.typemodl, \

                                             typenorm='edgeleft', \

                                             # plotting
                                             pathfoldanim=pathfoldanim, \
                                             typelang=typelang, \
                                             typefileplot=typefileplot, \
                                             
                                             typevisu=typevisu, \

                                             booldiag=booldiag, \

                                             typeverb=1, \

                                             boolintp=boolintp, \
                                             
                                             boolwritover=boolwritover, \
                                             strgextn=strgextn, \
                                             titlvisu=strgtitl, \

                                             # sizefigr=gdat.figrsizeydob, \
                                             # boolsingside=False, \
                                             # boolanim=gdat.boolanimorbt, \
    
                                            )
    
    for strgpopl in gdat.liststrgpopl:
        
        if strgpopl == 'exar':
            dictpopl = gdat.dictexar
        else:
            dictpopl = gdat.dictexof
        
        numbcomppopl = dictpopl['radicomp'].size
        indxtargpopl = np.arange(numbcomppopl)

        ### TSM and ESM
        numbsamppopl = 100
        dictlistplan = dict()
        for strgfeat in gdat.listfeatstarpopl:
            dictlistplan[strgfeat] = np.zeros((numbsamppopl, dictpopl['masscomp'].size)) + np.nan
            for k in range(dictpopl[strgfeat].size):
                meanvarb = dictpopl[strgfeat][k]
                if not np.isfinite(meanvarb):
                    continue
                if np.isfinite(dictpopl['stdv' + strgfeat][k]):
                    stdvvarb = dictpopl['stdv' + strgfeat][k]
                else:
                    stdvvarb = 0.
                
                dictlistplan[strgfeat][:, k] = tdpy.samp_gaustrun(numbsamppopl, meanvarb, stdvvarb, 0., np.inf)
                dictlistplan[strgfeat][:, k] /= np.mean(dictlistplan[strgfeat][:, k])
                dictlistplan[strgfeat][:, k] *= meanvarb
                
        #### TSM
        listtsmm = ephesos.retr_tsmm(dictlistplan['radicomp'], dictlistplan['tmptplan'], dictlistplan['masscomp'], \
                                                                                        dictlistplan['radistar'], dictlistplan['jmagsyst'])

        #### ESM
        listesmm = ephesos.retr_esmm(dictlistplan['tmptplan'], dictlistplan['tmptstar'], dictlistplan['radicomp'], dictlistplan['radistar'], \
                                                                                                                    dictlistplan['kmagsyst'])
        ## augment the 
        dictpopl['stdvtsmm'] = np.std(listtsmm, 0)
        dictpopl['tsmm'] = np.nanmedian(listtsmm, 0)
        dictpopl['stdvesmm'] = np.std(listesmm, 0)
        dictpopl['esmm'] = np.nanmedian(listesmm, 0)
        
        dictpopl['vesc'] = ephesos.retr_vesc(dictpopl['masscomp'], dictpopl['radicomp'])
        dictpopl['vesc0060'] = dictpopl['vesc'] / 6.
        
        objticrs = astropy.coordinates.SkyCoord(ra=dictpopl['rascstar']*astropy.units.degree, \
                                               dec=dictpopl['declstar']*astropy.units.degree, frame='icrs')
        
        # galactic longitude
        dictpopl['lgalstar'] = np.array([objticrs.galactic.l])[0, :]
        
        # galactic latitude
        dictpopl['bgalstar'] = np.array([objticrs.galactic.b])[0, :]
        
        # ecliptic longitude
        dictpopl['loecstar'] = np.array([objticrs.barycentricmeanecliptic.lon.degree])[0, :]
        
        # ecliptic latitude
        dictpopl['laecstar'] = np.array([objticrs.barycentricmeanecliptic.lat.degree])[0, :]

        dictpopl['stnomass'] = dictpopl['masscomp'] / dictpopl['stdvmasscomp']

        #dictpopl['boollive'] = ~dictpopl['boolfpos']
        dictpopl['boolterr'] = dictpopl['radicomp'] < 1.8
        dictpopl['boolhabicons'] = (dictpopl['inso'] < 1.01) & (dictpopl['inso'] > 0.35)
        dictpopl['boolhabiopti'] = (dictpopl['inso'] < 1.78) & (dictpopl['inso'] > 0.29)
        # unlocked
        dictpopl['boolunlo'] = np.log10(dictpopl['massstar']) < (-2 + 3 * (np.log10(dictpopl['smax']) + 1))
        # Earth as a transiting planet
        dictpopl['booleatp'] = abs(dictpopl['laecstar']) < 0.25

        ## Hill sphere
        ## angular momentum
    
        dictpopl['sage'] = 1. / 365.2422 / 24. / 3600. * (1. / 486.) * (0.008406 * dictpopl['smax'] / 0.027 / dictpopl['massstar']**(1. / 3.))**6
        dictpopl['timelock'] = (1. / 486.) * (dictpopl['smax'] / 0.027 / dictpopl['massstar']**(1. / 3.))**6

        #for strg in dictpopl.keys():
        #    print(strg)
        #    summgene(dictpopl[strg])
        #    print('')
        
        # from SETI
        dictpopl['metrplan'] = (0.99 * np.heaviside(dictpopl['numbplantranstar'] - 2, 1.) + 0.01)
        dictpopl['metrhzon'] = (0.99 * dictpopl['boolhabiopti'].astype(float) + 0.01)
        dictpopl['metrunlo'] = (0.99 * dictpopl['boolunlo'].astype(float) + 0.01)
        dictpopl['metrterr'] = (0.99 * dictpopl['boolterr'].astype(float) + 0.01)
        dictpopl['metrhabi'] = dictpopl['metrunlo'] * dictpopl['metrhzon'] * dictpopl['metrterr']
        dictpopl['metrseti'] = dictpopl['metrhabi'] * dictpopl['metrplan'] * dictpopl['distsyst']**(-2.)
        dictpopl['metrhzon'] /= np.nanmax(dictpopl['metrhzon'])
        dictpopl['metrhabi'] /= np.nanmax(dictpopl['metrhabi'])
        dictpopl['metrplan'] /= np.nanmax(dictpopl['metrplan'])
        dictpopl['metrseti'] /= np.nanmax(dictpopl['metrseti'])
        
        # period ratios
        ## all 
        gdat.listratiperi = []
        gdat.intgreso = []
        liststrgstarcomp = []
        for m in indxtargpopl:
            strgstar = dictpopl['namestar'][m]
            if not strgstar in liststrgstarcomp:
                indxexarstar = np.where(dictpopl['namestar'] == strgstar)[0]
                if indxexarstar[0] != m:
                    raise Exception('')
                
                listperi = dictpopl['pericomp'][None, indxexarstar]
                if not np.isfinite(listperi).all() or np.where(listperi == 0)[0].size > 0:
                    liststrgstarcomp.append(strgstar)
                    continue
                intgreso, ratiperi = ephesos.retr_reso(listperi)
                
                numbcomp = indxexarstar.size
                
                gdat.listratiperi.append(ratiperi[0, :, :][np.triu_indices(numbcomp, k=1)])
                gdat.intgreso.append(intgreso)
                
                liststrgstarcomp.append(strgstar)
        
        gdat.listratiperi = np.concatenate(gdat.listratiperi)
        figr, axis = plt.subplots(figsize=gdat.figrsize)
        bins = np.linspace(1., 10., 400)
        axis.hist(gdat.listratiperi, bins=bins, rwidth=1)
        if gmod.numbcomp > 1:
            ## this system
            for j in gmod.indxcomp:
                for jj in gmod.indxcomp:
                    if gdat.dicterrr['pericomp'][0, j] > gdat.dicterrr['pericomp'][0, jj]:
                        ratiperi = gdat.dicterrr['pericomp'][0, j] / gdat.dicterrr['pericomp'][0, jj]
                        axis.axvline(ratiperi, color=gdat.listcolrcomp[jj])
                        axis.axvline(ratiperi, color=gdat.listcolrcomp[j], ls='--')
        
        ylim = axis.get_ylim()
        ydatlabl = 0.9 * ylim[1] + ylim[0]
        ## resonances
        for perifrst, periseco in [[2., 1.], [3., 2.], [4., 3.], [5., 4.], [5., 3.], [5., 2.]]:
            rati = perifrst / periseco
            axis.text(rati + 0.05, ydatlabl, '%d:%d' % (perifrst, periseco), size=8, color='grey', va='center', ha='center')
            axis.axvline(perifrst / periseco, color='grey', ls='--', alpha=0.5)
        #axis.set_xscale('log')
        axis.set_xlim([0.9, 2.7])
        axis.set_ylabel('N')
        axis.set_xlabel('Period ratio')
        plt.subplots_adjust(bottom=0.2)
        plt.subplots_adjust(left=0.2)
        path = pathvisufeatplan + 'histratiperi_%s_%s_%s.%s' % (gdat.strgtarg, strgpdfn, strgpopl, gdat.typefileplot)
        #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
        print('Writing to %s...' % path)
        plt.savefig(path)
        plt.close()
        
        # metastable helium absorption
        path = gdat.pathbasemile + '/data/wasp107b_transmission_spectrum.dat'
        if gdat.typeverb > 0:
            print('Reading from %s...' % path)
        arry = np.loadtxt(path, delimiter=',', skiprows=1)
        wlenwasp0107 = arry[:, 0]
        deptwasp0107 = arry[:, 1]
        deptstdvwasp0107 = arry[:, 2]
        
        stdvnirs = 0.24e-2
        for a in range(2):
            duratranplanwasp0107 = 2.74
            jmagsystwasp0107 = 9.4
            if a == 1:
                radicomp = gdat.dicterrr['radicomp'][0, :]
                masscomp = gdat.dicterrr['masscompused'][0, :]
                tmptplan = gdat.dicterrr['tmptplan'][0, :]
                duratranplan = gdat.dicterrr['duratrantotl'][0, :]
                radistar = gdat.radistar
                jmagsyst = gdat.jmagsyst
            else:
                print('WASP-107')
                radicomp = 0.924 * gdat.dictfact['rjre']
                masscomp = 0.119
                tmptplan = 736
                radistar = 0.66 # [R_S]
                jmagsyst = jmagsystwasp0107
                duratranplan = duratranplanwasp0107
            scalheig = ephesos.retr_scalheig(tmptplan, masscomp, radicomp)
            deptscal = 1e3 * 2. * radicomp * scalheig / radistar**2 # [ppt]
            dept = 80. * deptscal
            factstdv = np.sqrt(10**((-jmagsystwasp0107 + jmagsyst) / 2.5) * duratranplanwasp0107 / duratranplan)
            stdvnirsthis = factstdv * stdvnirs
            for b in np.arange(1, 6):
                stdvnirsscal = stdvnirsthis / np.sqrt(float(b))
                sigm = dept / stdvnirsscal
        
            print('radicomp')
            print(radicomp)
            print('masscomp')
            print(masscomp)
            print('duratranplan')
            print(duratranplan)
            print('tmptplan')
            print(tmptplan)
            print('jmagsyst')
            print(jmagsyst)
            print('jmagsystwasp0107')
            print(jmagsystwasp0107)
            print('scalheig [R_E]')
            print(scalheig)
            print('scalheig [km]')
            print(scalheig * 71398)
            print('deptscal')
            print(deptscal)
            print('depttrancomp')
            print(dept)
            print('duratranplanwasp0107')
            print(duratranplanwasp0107)
            print('duratranplan')
            print(duratranplan)
            print('factstdv')
            print(factstdv)
            print('stdvnirsthis')
            print(stdvnirsthis)
            for b in np.arange(1, 6):
                print('With %d transits:' % b)
                print('stdvnirsscal')
                print(stdvnirsscal)
                print('sigm')
                print(sigm)
        print('James WASP107b scale height: 855 km')
        print('James WASP107b scale height: %g [R_E]' % (855. / 71398))
        print('James WASP107b depth per scale height: 5e-4')
        print('ampltide ratio fact: deptthis / 500e-6')
        fact = deptscal / 500e-6
        print('fact')
        print(fact)
        # 2 A * Rp * H / Rs**2
            
        figr, axis = plt.subplots(figsize=gdat.figrsize)
        #axis.errorbar(wlenwasp0107, deptwasp0107, yerr=deptstdvwasp0107, ls='', ms=1, lw=1, marker='o', color='k', alpha=1)
        axis.errorbar(wlenwasp0107-10833, deptwasp0107*fact[0], yerr=deptstdvwasp0107*factstdv[0], ls='', ms=1, lw=1, marker='o', color='k', alpha=1)
        axis.set_xlabel(r'Wavelength - 10,833 [$\AA$]')
        axis.set_ylabel('Depth [\%]')
        plt.subplots_adjust(bottom=0.2, left=0.2)
        path = pathvisudataplan + 'dept_%s_%s.%s' % (gdat.strgtarg, strgpdfn, gdat.typefileplot)
        #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
        print('Writing to %s...' % path)
        plt.savefig(path)
        plt.close()

        # optical magnitude vs number of planets
        for b in range(4):
            if b == 0:
                strgvarbmagt = 'vmag'
                lablxaxi = 'V Magnitude'
                varbtarg = gdat.vmagsyst
                varb = dictpopl['vmagsyst']
            if b == 1:
                strgvarbmagt = 'jmag'
                lablxaxi = 'J Magnitude'
                varbtarg = gdat.jmagsyst
                varb = dictpopl['jmagsyst']
            if b == 2:
                strgvarbmagt = 'rvelsemascal_vmag'
                lablxaxi = '$K^{\prime}_{V}$'
                varbtarg = np.sqrt(10**(-gdat.vmagsyst / 2.5)) / gdat.massstar**(2. / 3.)
                varb = np.sqrt(10**(-dictpopl['vmagsyst'] / 2.5)) / dictpopl['massstar']**(2. / 3.)
            if b == 3:
                strgvarbmagt = 'rvelsemascal_jmag'
                lablxaxi = '$K^{\prime}_{J}$'
                varbtarg = np.sqrt(10**(-gdat.vmagsyst / 2.5)) / gdat.massstar**(2. / 3.)
                varb = np.sqrt(10**(-dictpopl['jmagsyst'] / 2.5)) / dictpopl['massstar']**(2. / 3.)
            for a in range(2):
                figr, axis = plt.subplots(figsize=gdat.figrsize)
                if a == 0:
                    indx = np.where((dictpopl['numbplanstar'] > 3))[0]
                if a == 1:
                    indx = np.where((dictpopl['numbplantranstar'] > 3))[0]
                
                if (b == 2 or b == 3):
                    normfact = max(varbtarg, np.nanmax(varb[indx]))
                else:
                    normfact = 1.
                varbtargnorm = varbtarg / normfact
                varbnorm = varb[indx] / normfact
                axis.scatter(varbnorm, dictpopl['numbplanstar'][indx], s=1, color='black')
                
                indxsort = np.argsort(varbnorm)
                if b == 2 or b == 3:
                    indxsort = indxsort[::-1]

                listnameaddd = []
                cntr = 0
                maxmnumbname = min(5, varbnorm.size)
                while True:
                    k = indxsort[cntr]
                    nameadd = dictpopl['namestar'][indx][k]
                    if not nameadd in listnameaddd:
                        axis.text(varbnorm[k], dictpopl['numbplanstar'][indx][k] + 0.5, nameadd, size=6, \
                                                                                                va='center', ha='right', rotation=45)
                        listnameaddd.append(nameadd)
                    cntr += 1
                    if len(listnameaddd) == maxmnumbname: 
                        break
                axis.scatter(varbtargnorm, gmod.numbcomp, s=5, color='black', marker='x')
                axis.text(varbtargnorm, gmod.numbcomp + 0.5, gdat.labltarg, size=8, color='black', \
                                                                                            va='center', ha='center', rotation=45)
                axis.set_ylabel(r'Number of transiting planets')
                axis.set_xlabel(lablxaxi)
                plt.subplots_adjust(bottom=0.2)
                plt.subplots_adjust(left=0.2)
                path = pathvisufeatsyst + '%snumb_%s_%s_%s_%d.%s' % (strgvarbmagt, gdat.strgtarg, strgpdfn, strgpopl, a, gdat.typefileplot)
                #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                print('Writing to %s...' % path)
                plt.savefig(path)
                plt.close()

                figr, axis = plt.subplots(figsize=gdat.figrsize)
                axis.hist(varbnorm, 50)
                axis.axvline(varbtargnorm, color='black', ls='--')
                axis.text(0.3, 0.9, gdat.labltarg, size=8, color='black', transform=axis.transAxes, va='center', ha='center')
                axis.set_ylabel(r'Number of systems')
                axis.set_xlabel(lablxaxi)
                plt.subplots_adjust(bottom=0.2)
                plt.subplots_adjust(left=0.2)
                path = pathvisufeatsyst + 'hist_%s_%s_%s_%s_%d.%s' % (strgvarbmagt, gdat.strgtarg, strgpdfn, strgpopl, a, gdat.typefileplot)
                #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                print('Writing to %s...' % path)
                plt.savefig(path)
                plt.close()
            
        # planet feature distribution plots
        print('Will make the relevant distribution plots...')
        numbcomptext = min(10, numbcomppopl)
        liststrgtext = ['notx', 'text']
        
        # first is x-axis, second is y-axis
        liststrgfeatpairplot = [ \
                            #['smax', 'massstar'], \
                            #['rascstar', 'declstar'], \
                            #['lgalstar', 'bgalstar'], \
                            #['loecstar', 'laecstar'], \
                            #['distsyst', 'vmagsyst'], \
                            #['inso', 'radicomp'], \
                            ['radicomp', 'tmptplan'], \
                            ['radicomp', 'tsmm'], \
                            #['radicomp', 'esmm'], \
                            ['tmptplan', 'tsmm'], \
                            #['tagestar', 'vesc'], \
                            ['tmptplan', 'vesc0060'], \
                            #['radicomp', 'tsmm'], \
                            #['tmptplan', 'vesc'], \
                            #['pericomp', 'inso'], \
                            #['radistar', 'radicomp'], \
                            #['tmptplan', 'radistar'], \
                            #['projoblq', 'vsiistar'], \
                           ]
        
        numbpairfeatplot = len(liststrgfeatpairplot)

        indxpairfeatplot = np.arange(numbpairfeatplot)
        liststrgsort = ['none', \
                        #'esmm', \
                        'tsmm', \
                        #'metrhzon', 'metrhabi', 'metrplan', 'metrseti', \
                       ]
        numbstrgsort = len(liststrgsort)
        indxstrgsort = np.arange(numbstrgsort)

        indxcompfilt = dict()
        indxcompfilt['totl'] = indxtargpopl
        
        #indxcompfilt['tran'] = np.where(dictpopl['booltran'])[0]
        strgcuttmain = 'totl'
        
        #indxcompfilt['box1'] = np.where((dictpopl['radicomp'] < 3.5) & (dictpopl['radicomp'] > 3.) & (dictpopl['tmptplan'] > 300) & \
        #                                                                                            (dictpopl['tmptplan'] < 500) & dictpopl['booltran'])[0]
        #indxcompfilt['box2'] = np.where((dictpopl['radicomp'] < 2.5) & (dictpopl['radicomp'] > 2.) & (dictpopl['tmptplan'] > 800) & \
        #                                                                                            (dictpopl['tmptplan'] < 1000) & dictpopl['booltran'])[0]
        #indxcompfilt['box2'] = np.where((dictpopl['radicomp'] < 3.) & (dictpopl['radicomp'] > 2.5) & (dictpopl['tmptplan'] > 1000) & \
        #                                                                                            (dictpopl['tmptplan'] < 1400) & dictpopl['booltran'])[0]
        #indxcompfilt['box3'] = np.where((dictpopl['radicomp'] < 3.) & (dictpopl['radicomp'] > 2.5) & (dictpopl['tmptplan'] > 1000) & \
        #                                                                                            (dictpopl['tmptplan'] < 1400) & dictpopl['booltran'])[0]
        #indxcompfilt['r4tr'] = np.where((dictpopl['radicomp'] < 4) & dictpopl['booltran'])[0]
        #indxcompfilt['r4trtess'] = np.where((dictpopl['radicomp'] < 4) & dictpopl['booltran'] & \
        #                                                                (dictpopl['facidisc'] == 'Transiting Exoplanet Survey Satellite (TESS)'))[0]

        #indxcompfilt['r154'] = np.where((dictpopl['radicomp'] > 1.5) & (dictpopl['radicomp'] < 4))[0]
        #indxcompfilt['r204'] = np.where((dictpopl['radicomp'] > 2) & (dictpopl['radicomp'] < 4))[0]
        #indxcompfilt['rb24'] = np.where((dictpopl['radicomp'] < 4) & (dictpopl['radicomp'] > 2.))[0]
        #indxcompfilt['gmtr'] = np.where(np.isfinite(stnomass) & (stnomass > 5) & (dictpopl['booltran']))[0]
        #indxcompfilt['tran'] = np.where(dictpopl['booltran'])[0]
        #indxcompfilt['mult'] = np.where(dictpopl['numbplantranstar'] > 3)[0]
        #indxcompfilt['live'] = np.where(dictpopl['boollive'])[0]
        #indxcompfilt['terr'] = np.where(dictpopl['boolterr'] & dictpopl['boollive'])[0]
        #indxcompfilt['hzoncons'] = np.where(dictpopl['boolhabicons'] & dictpopl['boollive'])[0]
        #indxcompfilt['hzonopti'] = np.where(dictpopl['boolhabiopti'] & dictpopl['boollive'])[0]
        #indxcompfilt['unlo'] = np.where(dictpopl['boolunlo'] & dictpopl['boollive'])[0]
        #indxcompfilt['habi'] = np.where(dictpopl['boolterr'] & dictpopl['boolhabiopti'] & dictpopl['boolunlo'] & dictpopl['boollive'])[0]
        #indxcompfilt['eatp'] = np.where(dictpopl['booleatp'] & dictpopl['boollive'])[0]
        #indxcompfilt['seti'] = np.where(dictpopl['boolterr'] & dictpopl['boolhabicons'] & dictpopl['boolunlo'] & \
                                                                                            #dictpopl['booleatp'] & dictpopl['boollive'])[0]
        dicttemp = dict()
        dicttempmerg = dict()
        
        liststrgcutt = indxcompfilt.keys()
        
        liststrgvarb = [ \
                        'pericomp', 'inso', 'vesc0060', 'masscomp', \
                        'metrhzon', 'metrterr', 'metrplan', 'metrunlo', 'metrseti', \
                        'smax', \
                        'tmptstar', \
                        'rascstar', 'declstar', \
                        'loecstar', 'laecstar', \
                        'radistar', \
                        'massstar', \
                        'metastar', \
                        'radicomp', 'tmptplan', \
                        'metrhabi', 'metrplan', \
                        'lgalstar', 'bgalstar', 'distsyst', 'vmagsyst', \
                        'tsmm', 'esmm', \
                        'vsiistar', 'projoblq', \
                        'jmagsyst', \
                        'tagestar', \
                       ]

        listlablvarb, listscalpara = tdpy.retr_listlablscalpara(liststrgvarb)
        listlablvarbtotl = tdpy.retr_labltotl(listlablvarb)
        #listlablvarb = [ \
        #                ['P', 'days'], ['F', '$F_E$'], ['$v_{esc}^\prime$', 'kms$^{-1}$'], ['$M_p$', '$M_E$'], \
        #                [r'$\rho$_{HZ}', ''], [r'$\rho$_{T}', ''], [r'$\rho$_{MP}', ''], [r'$\rho$_{TL}', ''], [r'$\rho$_{SETI}', ''], \
        #                ['$a$', 'AU'], \
        #                ['$T_{eff}$', 'K'], \
        #                ['RA', 'deg'], ['Dec', 'deg'], \
        #                ['Ec. lon.', 'deg'], ['Ec. lat.', 'deg'], \
        #                ['$R_s$', '$R_S$'], \
        #                ['$M_s$', '$M_S$'], \
        #                ['[Fe/H]', 'dex'], \
        #                ['$R_p$', '$R_E$'], ['$T_p$', 'K'], \
        #                [r'$\rho_{SH}$', ''], [r'$\rho_{SP}$', ''], \
        #                ['$l$', 'deg'], ['$b$', 'deg'], ['$d$', 'pc'], ['$V$', ''], \
        #                ['TSM', ''], ['ESM', ''], \
        #                ['$v$sin$i$', 'kms$^{-1}$'], ['$\lambda$', 'deg'], \
        #                ['J', 'mag'], \
        #                ['$t_\star$', 'Gyr'], \
        #               ] 
        
        numbvarb = len(liststrgvarb)
        indxvarb = np.arange(numbvarb)
            
        # merge the target with the population
        for k, strgxaxi in enumerate(liststrgvarb + ['nameplan']):
            if not strgxaxi in dictpopl or not strgxaxi in gdat.dicterrr:
                continue
            dicttempmerg[strgxaxi] = np.concatenate([dictpopl[strgxaxi][indxcompfilt[strgcuttmain]], gdat.dicterrr[strgxaxi][0, :]])
        
        if not 'nameplan' in dictpopl:
            raise Exception('')

        #if not 'nameplan' in gdat.dicterrr:
        #    raise Exception('')

        if not 'nameplan' in dicttempmerg:
            raise Exception('')

        for k, strgxaxi in enumerate(liststrgvarb):
            
            if strgxaxi == 'tmptplan':
                print('strgxaxi in dictpopl')
                print(strgxaxi in dictpopl)
                print('strgxaxi in gdat.dicterrr')
                print(strgxaxi in gdat.dicterrr)
                raise Exception('')

            if not strgxaxi in dictpopl:
                continue

            if not strgxaxi in gdat.dicterrr:
                continue

            if not 'tmptplan' in dicttempmerg:
                print('dicttempmerg')
                print(dicttempmerg.keys())
                raise Exception('')

            for m, strgyaxi in enumerate(liststrgvarb):
                
                booltemp = False
                for l in indxpairfeatplot:
                    if strgxaxi == liststrgfeatpairplot[l][0] and strgyaxi == liststrgfeatpairplot[l][1]:
                        booltemp = True
                if not booltemp:
                    continue
                 
                # to be deleted
                #for strgfeat, valu in dictpopl.items():
                    #dicttempmerg[strgfeat] = np.concatenate([dictpopl[strgfeat][indxcompfilt[strgcuttmain]], gdat.dicterrr[strgfeat][0, :]])
                
                for strgcutt in liststrgcutt:
                    
                    # merge population with the target
                    #for strgfeat, valu in dictpopl.items():
                    #    dicttemp[strgfeat] = np.concatenate([dictpopl[strgfeat][indxcompfilt[strgcutt]], gdat.dicterrr[strgfeat][0, :]])
                    
                    liststrgfeatcsvv = [ \
                                        #'inso', 'metrhzon', 'radicomp', 'metrterr', 'massstar', 'smax', 'metrunlo', 'distsyst', 'metrplan', 'metrseti', \
                                        'rascstar', 'declstar', 'radicomp', 'masscomp', 'tmptplan', 'jmagsyst', 'radistar', 'tsmm', \
                                       ]
                    for y in indxstrgsort:
                        
                        if liststrgsort[y] != 'none':
                        
                            indxgood = np.where(np.isfinite(dicttempmerg[liststrgsort[y]]))[0]
                            indxsort = np.argsort(dicttempmerg[liststrgsort[y]][indxgood])[::-1]
                            indxcompsort = indxgood[indxsort]
                            
                            path = gdat.pathdatatarg + '%s_%s_%s.csv' % (strgpopl, strgcutt, liststrgsort[y])
                            objtfile = open(path, 'w')
                            
                            strghead = '%4s, %20s' % ('Rank', 'Name')
                            for strgfeatcsvv in liststrgfeatcsvv:
                                strghead += ', %12s' % listlablvarbtotl[liststrgvarb.index(strgfeatcsvv)]
                            strghead += '\n'
                            
                            objtfile.write(strghead)
                            cntr = 1
                            for l in indxcompsort:
                                
                                strgline = '%4d, %20s' % (cntr, dicttempmerg['nameplan'][l])
                                for strgfeatcsvv in liststrgfeatcsvv:
                                    strgline += ', %12.4g' % dicttempmerg[strgfeatcsvv][l]
                                strgline += '\n'
                                
                                objtfile.write(strgline)
                                cntr += 1 
                            print('Writing to %s...' % path)
                            objtfile.close()
                    
                        if gdat.boolplotpopl:
                            # repeat, one without text, one with text
                            for b, strgtext in enumerate(liststrgtext):
                                figr, axis = plt.subplots(figsize=gdat.figrsize)
                                
                                if liststrgsort[y] != 'none' and strgtext != 'text' or liststrgsort[y] == 'none' and strgtext == 'text':
                                    continue
                        
                                ## population
                                if strgcutt == strgcuttmain:
                                    axis.errorbar(dicttempmerg[strgxaxi], dicttempmerg[strgyaxi], ls='', ms=1, marker='o', color='k')
                                else:
                                    axis.errorbar(dicttempmerg[strgxaxi], dicttempmerg[strgyaxi], ls='', ms=1, marker='o', color='k')
                                    #axis.errorbar(dicttemp[strgxaxi], dicttemp[strgyaxi], ls='', ms=2, marker='o', color='r')
                                
                                ## this system
                                for j in gmod.indxcomp:
                                    if strgxaxi in gdat.dicterrr:
                                        xdat = gdat.dicterrr[strgxaxi][0, j, None]
                                        xerr = gdat.dicterrr[strgxaxi][1:3, j, None]
                                    if strgyaxi in gdat.dicterrr:
                                        ydat = gdat.dicterrr[strgyaxi][0, j, None]
                                        yerr = gdat.dicterrr[strgyaxi][1:3, j, None]
                                    
                                    # temp apply cut on this system
                                    
                                    if strgxaxi in gdat.listfeatstar and strgyaxi in gdat.listfeatstar:
                                        axis.errorbar(xdat, ydat, color='k', lw=1, xerr=xerr, yerr=yerr, ls='', marker='o', ms=6, zorder=2)
                                        axis.text(0.85, 0.9 - j * 0.08, gdat.labltarg, color='k', \
                                                                                              va='center', ha='center', transform=axis.transAxes)
                                        break
                                    else:
                                        
                                        if not strgxaxi in gdat.dicterrr and strgyaxi in gdat.dicterrr:
                                            if strgyaxi in gdat.listfeatstar:
                                                axis.axhline(ydat, color='k', lw=1, ls='--', zorder=2)
                                                axis.text(0.85, 0.9 - j * 0.08, gdat.labltarg, color='k', \
                                                                                              va='center', ha='center', transform=axis.transAxes)
                                                break
                                            else:
                                                axis.axhline(ydat, color=gdat.listcolrcomp[j], lw=1, ls='--', zorder=2)
                                        if not strgyaxi in gdat.dicterrr and strgxaxi in gdat.dicterrr:
                                            if strgxaxi in gdat.listfeatstar:
                                                axis.axvline(xdat, color='k', lw=1, ls='--', zorder=2)
                                                axis.text(0.85, 0.9 - j * 0.08, gdat.labltarg, color='k', \
                                                                                              va='center', ha='center', transform=axis.transAxes)
                                                break
                                            else:
                                                axis.axvline(xdat, color=gdat.listcolrcomp[j], lw=1, ls='--')
                                        if strgxaxi in gdat.dicterrr and strgyaxi in gdat.dicterrr:
                                            axis.errorbar(xdat, ydat, color=gdat.listcolrcomp[j], lw=1, xerr=xerr, yerr=yerr, ls='', marker='o', \
                                                                                                                                zorder=2, ms=6)
                                        
                                        if strgxaxi in gdat.dicterrr or strgyaxi in gdat.dicterrr:
                                            axis.text(0.85, 0.9 - j * 0.08, r'\textbf{%s}' % gdat.liststrgcomp[j], color=gdat.listcolrcomp[j], \
                                                                                            va='center', ha='center', transform=axis.transAxes)
                                
                                # include text
                                if liststrgsort[y] != 'none' and strgtext == 'text':
                                    for ll, l in enumerate(indxcompsort):
                                        if ll < numbcomptext:
                                            text = '%s' % dicttemp['nameplan'][l]
                                            xdat = dicttemp[strgxaxi][l]
                                            ydat = dicttemp[strgyaxi][l]
                                            if np.isfinite(xdat) and np.isfinite(ydat):
                                                objttext = axis.text(xdat, ydat, text, size=1, ha='center', va='center')
                                
                                if strgxaxi == 'tmptplan' and strgyaxi == 'vesc0060':
                                    xlim = [0, 0]
                                    xlim[0] = 0.5 * np.nanmin(dictpopl['tmptplan'])
                                    xlim[1] = 2. * np.nanmax(dictpopl['tmptplan'])
                                    arrytmptplan = np.linspace(xlim[0], xlim[1], 1000)
                                    cons = [1., 4., 16., 18., 28., 44.] # H, He, CH4, H20, CO, CO2
                                    for i in range(len(cons)):
                                        arryyaxi = (arrytmptplan / 40. / cons[i])**0.5
                                        axis.plot(arrytmptplan, arryyaxi, color='grey', alpha=0.5)
                                    axis.set_xlim(xlim)

                                if strgxaxi == 'radicomp' and strgyaxi == 'masscomp':
                                    gdat.listlabldenscomp = ['Earth-like', 'Pure Water', 'Pure Iron']
                                    listdenscomp = [1., 0.1813, 1.428]
                                    listposicomp = [[13., 2.6], [4.7, 3.5], [13., 1.9]]
                                    gdat.numbdenscomp = len(gdat.listlabldenscomp)
                                    gdat.indxdenscomp = np.arange(gdat.numbdenscomp)
                                    masscompdens = np.linspace(0.5, 16.) # M_E
                                    for i in gdat.indxdenscomp:
                                        radicompdens = (masscompdens / listdenscomp[i])**(1. / 3.)
                                        axis.plot(masscompdens, radicompdens, color='grey')
                                    for i in gdat.indxdenscomp:
                                        axis.text(listposicomp[i][0], listposicomp[i][1], gdat.listlabldenscomp[i])
                                
                                #if strgxaxi == 'tmptplan':
                                #    axis.axvline(273., ls='--', alpha=0.3, color='k')
                                #    axis.axvline(373., ls='--', alpha=0.3, color='k')
                                #if strgyaxi == 'tmptplan':
                                #    axis.axhline(273., ls='--', alpha=0.3, color='k')
                                #    axis.axhline(373., ls='--', alpha=0.3, color='k')
        
                                axis.set_xlabel(listlablvarbtotl[k])
                                axis.set_ylabel(listlablvarbtotl[m])
                                if listscalpara[k] == 'logt':
                                    axis.set_xscale('log')
                                if listscalpara[m] == 'logt':
                                    axis.set_yscale('log')
                                
                                plt.subplots_adjust(left=0.2)
                                plt.subplots_adjust(bottom=0.2)
                                pathvisufeatplan = getattr(gdat, 'pathvisufeatplan' + strgpdfn)
                                path = pathvisufeatplan + 'feat_%s_%s_%s_%s_%s_%s_%s_%s.%s' % \
                                             (strgxaxi, strgyaxi, gdat.strgtarg, strgpopl, strgcutt, \
                                                                                   strgtext, liststrgsort[y], strgpdfn, gdat.typefileplot)
                                #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.5, 0.1]})
                                print('Writing to %s...' % path)
                                plt.savefig(path)
                                plt.close()

   
def bdtr_wrap(gdat, b, p, y, epocmask, perimask, duramask, strgintp, strgoutp, strgtren, timescalbdtrspln):
    '''
    Wrap baseline-detrending function of ephesos for miletos
    '''
    
    # output
    gdat.listarrytser[strgoutp][b][p][y] = np.copy(gdat.listarrytser[strgintp][b][p][y])
    
    # trend
    gdat.listarrytser[strgtren][b][p][y] = np.copy(gdat.listarrytser[strgintp][b][p][y])
    
    for e in gdat.indxener[p]:
        gdat.rflxbdtrregi, gdat.listindxtimeregi[b][p][y], gdat.indxtimeregioutt[b][p][y], gdat.listobjtspln[b][p][y], gdat.listtimebrek = \
                     ephesos.bdtr_tser(gdat.listarrytser[strgintp][b][p][y][:, e, 0], gdat.listarrytser[strgintp][b][p][y][:, e, 1], \
                                                stdvlcur=gdat.listarrytser[strgintp][b][p][y][:, e, 2], \
                                                epocmask=epocmask, perimask=perimask, duramask=duramask, \
                                                timescalbdtrspln=timescalbdtrspln, \
                                                typeverb=gdat.typeverb, \
                                                timeedge=gdat.listtimebrek, \
                                                timebrekregi=gdat.timebrekregi, \
                                                ordrspln=gdat.ordrspln, \
                                                timescalbdtrmedi=gdat.timescalbdtrmedi, \
                                                boolbrekregi=gdat.boolbrekregi, \
                                                typebdtr=gdat.typebdtr, \
                                                )
    
        gdat.listarrytser[strgoutp][b][p][y][:, e, 1] = np.concatenate(gdat.rflxbdtrregi)
    
    numbsplnregi = len(gdat.rflxbdtrregi)
    gdat.indxsplnregi[b][p][y] = np.arange(numbsplnregi)


def plot_tsercore(gdat, strgmodl, strgarry, b, p, y=None, boolcolrtran=True, boolflar=False):
    
    gmod = getattr(gdat, strgmodl)
    
    boolchun = y is not None
    
    if not boolchun and gdat.numbchun[b][p] == 1:
        return
        
    if boolchun:
        arrytser = gdat.listarrytser[strgarry][b][p][y]
    else:
        arrytser = gdat.arrytser[strgarry][b][p]
    
    if gdat.booldiag:
        if len(arrytser) == 0:
            print('')
            print('strgarry')
            print(strgarry)
            print('arrytser')
            print(arrytser)
            raise Exception('')
    
    # determine name of the file
    ## string indicating the prior on the transit ephemerides
    strgprioplan = ''
    if strgarry != 'raww' and gdat.typepriocomp is not None:
        strgprioplan = '_%s' % gdat.typepriocomp
    strgcolr = ''
    if boolcolrtran:
        strgcolr = '_colr'
    strgchun = ''
    if boolchun:
        strgchun = '_' + gdat.liststrgchun[b][p][y]
    path = gdat.pathvisutarg + '%s%s_%s%s_%s%s_%s%s.%s' % \
                    (gdat.liststrgtser[b], gdat.strgcnfg, strgarry, strgcolr, gdat.liststrginst[b][p], strgchun, gdat.strgtarg, strgprioplan, gdat.typefileplot)
    
    if not strgarry.startswith('bdtroutpit') and not strgarry.startswith('clipoutpit'):
        if strgarry == 'raww':
            limt = [0., 0.9, 0.5, 0.1]
        elif strgarry == 'bdtr':
            limt = [0., 0.7, 0.5, 0.1]
        else:
            limt = [0., 0.5, 0.5, 0.1]
        gdat.listdictdvrp[0].append({'path': path, 'limt':limt})
        
    if not os.path.exists(path):
            
        figr, axis = plt.subplots(figsize=gdat.figrsizeydobskin)
        
        if arrytser.shape[1] > 1:
            extent = [gdat.listener[p][0], gdat.listener[p][1], arrytser[0, 0, 0] - gdat.timeoffs, arrytser[-1, 0, 0] - gdat.timeoffs]
            imag = axis.imshow(arrytser[:, :, 1].T, extent=extent)
        else:
            axis.plot(arrytser[:, 0, 0] - gdat.timeoffs, arrytser[:, 0, 1], color='grey', marker='.', ls='', ms=1, rasterized=True)
        
        if boolcolrtran:
            # color and name transits
            ylim = axis.get_ylim()
            listtimetext = []
            for j in gmod.indxcomp:
                if boolchun:
                    indxtime = gdat.listindxtimetranchun[j][b][p][y] 
                else:
                    if y > 0:
                        continue
                    indxtime = gdat.listindxtimetran[j][b][p][0]
                
                colr = gdat.listcolrcomp[j]
                # plot data
                axis.plot(arrytser[indxtime, 0] - gdat.timeoffs, arrytser[indxtime, 1], color=colr, marker='.', ls='', ms=1, rasterized=True)
                # draw planet names
                for n in np.linspace(-gdat.numbcyclcolrplot, gdat.numbcyclcolrplot, 2 * gdat.numbcyclcolrplot + 1):
                    time = gdat.epocmtracompprio[j] + n * gdat.pericompprio[j] - gdat.timeoffs
                    if np.where(abs(arrytser[:, 0] - gdat.timeoffs - time) < 0.1)[0].size > 0:
                        
                        # add a vertical offset if overlapping
                        if np.where(abs(np.array(listtimetext) - time) < 0.5)[0].size > 0:
                            ypostemp = ylim[0] + (ylim[1] - ylim[0]) * 0.95
                        else:
                            ypostemp = ylim[0] + (ylim[1] - ylim[0]) * 0.9

                        # draw the planet letter
                        axis.text(time, ypostemp, r'\textbf{%s}' % gdat.liststrgcomp[j], color=gdat.listcolrcomp[j], va='center', ha='center')
                        listtimetext.append(time)
        
        if boolchun:
            if boolflar:
                ydat = axis.get_ylim()[1]
                for kk in range(len(gdat.listindxtimeflar[p][y])):
                    ms = 0.5 * gdat.listmdetflar[p][y][kk]
                    axis.plot(arrytser[gdat.listindxtimeflar[p][y][kk], 0] - gdat.timeoffs, ydat, marker='v', color='b', ms=ms, rasterized=True)
                axis.plot(gdat.listarrytser['bdtrmedi'][b][p][y][:, 0, 0] - gdat.timeoffs, \
                          gdat.listarrytser['bdtrmedi'][b][p][y][:, 0, 1], \
                          color='g', marker='.', ls='', ms=1, rasterized=True)
                
                print('heeeey')
                print('heeeey')
                print('heeeey')
                print('heeeey')
                print('heeeey')
                print('heeeey')
                print('gdat.listarrytser[bdtrmedi][b][p][y]')
                summgene(gdat.listarrytser['bdtrmedi'][b][p][y])
                print('heeeey')
                print('heeeey')
                print('heeeey')
                print('heeeey')
                
                axis.fill_between(gdat.listarrytser['bdtrmedi'][b][p][y][:, 0, 0] - gdat.timeoffs, \
                                  gdat.listarrytser['bdtrlowr'][b][p][y][:, 0, 1], \
                                  gdat.listarrytser['bdtruppr'][b][p][y][:, 0, 1], \
                                  color='c', alpha=0.2, rasterized=True)
                axis.axhline(gdat.thrsrflxflar[p][y], ls='--', alpha=0.5, color='r')
            
        axis.set_xlabel('Time [BJD - %d]' % gdat.timeoffs)
        if arrytser.shape[1] > 1:
            axis.set_ylabel(gdat.lablener)
            cbar = plt.colorbar(imag)
        else:
            axis.set_ylabel(gdat.listlabltser[b])
        titl = '%s, %s' % (gdat.labltarg, gdat.listlablinst[b][p])
        if gdat.lablcnfg is not None and gdat.lablcnfg != '':
           titl += ', %s' % gdat.lablcnfg 
        if y is not None and len(gdat.listlablchun[b][p][y]) > 0 and gdat.listlablchun[b][p][y] != '':
           titl += ', %s' % gdat.listlablchun[b][p][y]
        axis.set_title(titl)
        plt.subplots_adjust(bottom=0.2)
        
        if gdat.typeverb > 0:
            print('Writing to %s...' % path)
        plt.savefig(path, dpi=200)
        plt.close()
    

    if gdat.numbener[p] > 1:
        # plot each energy
        
        path = gdat.pathvisutarg + '%s%s_%s%s_%s%s_%s%s_ener.%s' % \
                    (gdat.liststrgtser[b], gdat.strgcnfg, strgarry, strgcolr, gdat.liststrginst[b][p], strgchun, gdat.strgtarg, strgprioplan, gdat.typefileplot)
    
        if not os.path.exists(path):
                
            figr, axis = plt.subplots(figsize=gdat.figrsizeydobskin)
            
            sprdrflx = np.amax(np.std(arrytser[:, :, 1], 0)) * 5.
            listdiffrflxener = np.linspace(-1., 1., gdat.numbener[p]) * 0.5 * gdat.numbener[p] * sprdrflx

            for e in gdat.indxener[p]:
                color = plt.cm.rainbow(e / (gdat.numbener[p] - 1))
                axis.plot(arrytser[:, e, 0] - gdat.timeoffs, arrytser[:, e, 1] + listdiffrflxener[e], color=color, marker='.', ls='', ms=1, rasterized=True)
            
            if boolcolrtran:
                # color and name transits
                ylim = axis.get_ylim()
                listtimetext = []
                for j in gmod.indxcomp:
                    if boolchun:
                        indxtime = gdat.listindxtimetranchun[j][b][p][y] 
                    else:
                        if y > 0:
                            continue
                        indxtime = gdat.listindxtimetran[j][b][p][0]
                    
                    colr = gdat.listcolrcomp[j]
                    # plot data
                    axis.plot(arrytser[indxtime, 0] - gdat.timeoffs, arrytser[indxtime, 1], color=colr, marker='.', ls='', ms=1, rasterized=True)
                    # draw planet names
                    for n in np.linspace(-gdat.numbcyclcolrplot, gdat.numbcyclcolrplot, 2 * gdat.numbcyclcolrplot + 1):
                        time = gdat.epocmtracompprio[j] + n * gdat.pericompprio[j] - gdat.timeoffs
                        if np.where(abs(arrytser[:, 0] - gdat.timeoffs - time) < 0.1)[0].size > 0:
                            
                            # add a vertical offset if overlapping
                            if np.where(abs(np.array(listtimetext) - time) < 0.5)[0].size > 0:
                                ypostemp = ylim[0] + (ylim[1] - ylim[0]) * 0.95
                            else:
                                ypostemp = ylim[0] + (ylim[1] - ylim[0]) * 0.9

                            # draw the planet letter
                            axis.text(time, ypostemp, r'\textbf{%s}' % gdat.liststrgcomp[j], color=gdat.listcolrcomp[j], va='center', ha='center')
                            listtimetext.append(time)
            
            if boolchun:
                if boolflar:
                    ydat = axis.get_ylim()[1]
                    for kk in range(len(gdat.listindxtimeflar[p][y])):
                        ms = 0.5 * gdat.listmdetflar[p][y][kk]
                        axis.plot(arrytser[gdat.listindxtimeflar[p][y][kk], 0] - gdat.timeoffs, ydat, marker='v', color='b', ms=ms, rasterized=True)
                    axis.plot(gdat.listarrytser['bdtrmedi'][b][p][y][:, 0, 0] - gdat.timeoffs, \
                              gdat.listarrytser['bdtrmedi'][b][p][y][:, 0, 1], color='g', marker='.', ls='', ms=1, rasterized=True)
                    axis.fill_between(gdat.listarrytser['bdtrmedi'][b][p][y][:, 0, 0] - gdat.timeoffs, 
                                      gdat.listarrytser['bdtrlowr'][b][p][y][:, 0, 1], \
                                      gdat.listarrytser['bdtruppr'][b][p][y][:, 0, 1], \
                                      color='c', alpha=0.2, rasterized=True)
                    axis.axhline(gdat.thrsrflxflar[p][y], ls='--', alpha=0.5, color='r')
                
            axis.set_xlabel('Time [BJD - %d]' % gdat.timeoffs)
            axis.set_ylabel(gdat.listlabltser[b])
            axis.set_title(gdat.labltarg)
            plt.subplots_adjust(bottom=0.2)
            
            if gdat.typeverb > 0:
                print('Writing to %s...' % path)
            plt.savefig(path, dpi=200)
            plt.close()


def plot_tser(gdat, strgmodl, b, p, y, strgarry, booltoge=True, boolflar=False):
    
    gmod = getattr(gdat, strgmodl)
    
    # plot each chunk
    plot_tsercore(gdat, strgmodl, strgarry, b, p, y, boolcolrtran=False, boolflar=boolflar)
    
    # plot all chunks together if there is more than one chunk
    if y == 0 and gdat.numbchun[b][p] > 1 and booltoge:
        plot_tsercore(gdat, strgmodl, strgarry, b, p, boolcolrtran=False, boolflar=boolflar)
    
    # highlight times in-transit
    if strgarry != 'raww' and gdat.numbcompprio is not None:
        
        ## plot each chunk
        plot_tsercore(gdat, strgmodl, strgarry, b, p, y, boolcolrtran=True, boolflar=boolflar)
        
        ## plot all chunks together if there is more than one chunk
        if y == 0 and gdat.numbchun[b][p] > 1:
            plot_tsercore(gdat, strgmodl, strgarry, b, p, boolcolrtran=True, boolflar=boolflar)

        if b == 0:
            path = gdat.pathvisutarg + 'rflx%s_intr%s_%s_%s_%s.%s' % \
                                            (strgarry, gdat.strgcnfg, gdat.liststrginst[b][p], gdat.strgtarg, gdat.typepriocomp, gdat.typefileplot)
            if not os.path.exists(path):
                # plot only the in-transit data
                figr, axis = plt.subplots(gmod.numbcomp, 1, figsize=gdat.figrsizeydobskin, sharex=True)
                if gmod.numbcomp == 1:
                    axis = [axis]
                for jj, j in enumerate(gmod.indxcomp):
                    axis[jj].plot(gdat.arrytser[strgarry][b][p][gdat.listindxtimetran[j][b][p][0], 0] - gdat.timeoffs, \
                                                                         gdat.arrytser[strgarry][b][p][gdat.listindxtimetran[j][b][p][0], 1], \
                                                                                           color=gdat.listcolrcomp[j], marker='o', ls='', ms=0.2)
                
                axis[-1].set_ylabel(gdat.labltserphot)
                #axis[-1].yaxis.set_label_coords(0, gmod.numbcomp * 0.5)
                axis[-1].set_xlabel('Time [BJD - %d]' % gdat.timeoffs)
                
                #plt.subplots_adjust(bottom=0.2)
                #gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.8, 0.8]})
                print('Writing to %s...' % path)
                plt.savefig(path)
                plt.close()
        

def plot_tser_bdtr(gdat, b, p, y, z, r, strgarryinpt, strgarryoutp):
    '''
    Plot baseline detrending.
    '''
    
    ## string indicating the prior on the transit ephemerides
    strgprioplan = ''
    
    #if strgarry != 'raww' and gdat.typepriocomp is not None:
    #    strgprioplan = '_%s' % gdat.typepriocomp
    
    path = gdat.pathvisutarg + 'rflx_ts%02dit%02dsumm%s_%s_%s_%s%s%s.%s' % (z, r, gdat.strgcnfg, gdat.liststrginst[b][p], \
                                        gdat.liststrgchun[b][p][y], gdat.strgtarg, strgprioplan, gdat.liststrgener[p][gdat.indxenerclip], gdat.typefileplot)
    gdat.listdictdvrp[0].append({'path': path, 'limt':[0., 0.05, 1.0, 0.2]})
    if not os.path.exists(path):
            
        figr, axis = plt.subplots(2, 1, figsize=gdat.figrsizeydob)
        for i in gdat.indxsplnregi[b][p][y]:
            ## non-baseline-detrended light curve
            axis[0].plot(gdat.listarrytser[strgarryinpt][b][p][y][:, gdat.indxenerclip, 0] - gdat.timeoffs, \
                         gdat.listarrytser[strgarryinpt][b][p][y][:, gdat.indxenerclip, 1], rasterized=True, alpha=gdat.alphraww, \
                                                                                            marker='o', ls='', ms=1, color='grey')
            ## spline
            if gdat.listobjtspln[b][p][y] is not None and gdat.listobjtspln[b][p][y][i] is not None:
                minmtimeregi = gdat.listarrytser[strgarryinpt][b][p][y][0, gdat.indxenerclip, 0]
                maxmtimeregi = gdat.listarrytser[strgarryinpt][b][p][y][-1, gdat.indxenerclip, 0]
                timesplnregifine = np.linspace(minmtimeregi, maxmtimeregi, 1000)
                if gdat.typebdtr == 'spln':
                    lcurtren = gdat.listobjtspln[b][p][y][i](timesplnregifine)
                if gdat.typebdtr == 'gpro':
                    lcurtren = gdat.listobjtspln[b][p][y][i].predict(gdat.listarrytser[strgarryinpt][b][p][y][gdat.indxtimeregioutt[b][p][y][i], gdat.indxenerclip, 1], \
                                                                                                                        t=timesplnregifine, return_cov=False, return_var=False)
                axis[0].plot(timesplnregifine - gdat.timeoffs, lcurtren, 'b-', lw=3, rasterized=True)
            ## baseline-detrended light curve
            axis[1].plot(gdat.listarrytser[strgarryoutp][b][p][y][:, gdat.indxenerclip, 0] - gdat.timeoffs, \
                         gdat.listarrytser[strgarryoutp][b][p][y][:, gdat.indxenerclip, 1], rasterized=True, alpha=gdat.alphraww, \
                                                                                              marker='o', ms=1, ls='', color='grey')
        for a in range(2):
            axis[a].set_ylabel(gdat.labltserphot)
        axis[0].set_xticklabels([])
        axis[1].set_xlabel('Time [BJD - %d]' % gdat.timeoffs)
        plt.subplots_adjust(hspace=0.)
        print('Writing to %s...' % path)
        plt.savefig(path, dpi=200)
        plt.close()
                            

def retr_namebdtrclip(e, r):

    strgarrybdtrinpt = 'ts%02dit%02dbdtrinpt' % (e, r)
    strgarryclipinpt = 'ts%02dit%02dclipinpt' % (e, r)
    strgarryclipoutp = 'ts%02dit%02dclipoutp' % (e, r)
    strgarrybdtrblin = 'ts%02dit%02dbdtrblin' % (e, r)
    strgarrybdtroutp = 'ts%02dit%02dbdtroutp' % (e, r)

    return strgarrybdtrinpt, strgarryclipoutp, strgarrybdtroutp, strgarryclipinpt, strgarrybdtrblin


def setp_para(gdat, strgmodl, nameparabase, minmpara, maxmpara, lablpara, strgener=None, strgcomp=None, strglmdk=None, boolvari=True):
    
    gmod = getattr(gdat, strgmodl)
    
    nameparabasefinl = nameparabase
    
    if strgcomp is not None:
        nameparabasefinl += strgcomp

    if strglmdk is not None:
        nameparabasefinl += strglmdk

    if strgener is not None:
        nameparabasefinl += strgener

    if hasattr(gmod, nameparabasefinl):
        if gdat.typeverb > 0:
            print('%s has been fixed for %s to %g...' % (nameparabasefinl, strgmodl, getattr(gmod, nameparabasefinl)))
    
    gmod.listlablpara.append(lablpara)
    gmod.listminmpara.append(minmpara)
    gmod.listmaxmpara.append(maxmpara)
    gmod.dictfeatpara['scal'].append('self')
    
    # add the name of the parameter to the list of the parameters of the model
    ## all parameters
    gmod.listnameparafull += [nameparabasefinl]
    if gdat.booldiag:
        if strgmodl == 'true':
            if not hasattr(gdat.true, nameparabasefinl):
                print('')
                print('')
                print('')
                print('strgmodl')
                print(strgmodl)
                print('gdat.true.boolmodlpsys')
                print(gdat.true.boolmodlpsys)
                print('gmod.typemodlblinener')
                print(gmod.typemodlblinener)
                print('gmod.typemodlblinshap')
                print(gmod.typemodlblinshap)
                print('nameparabasefinl')
                print(nameparabasefinl)
                raise Exception('The true model parameter you are defining lacks the default value!')

    if boolvari and strgmodl == 'fitt':
        ## varied parameters
        gmod.listnameparafullvari += [nameparabasefinl]
    
        print('setp_para: Setting up gmod.dictindxpara[%s] of %s with gmod.cntr=%d...' % (nameparabasefinl, strgmodl, gmod.cntr))
    
        gmod.dictindxpara[nameparabasefinl] = gmod.cntr
    
        #if strgener is not None:
        #    if gdat.fitt.typemodlenerfitt == 'full':
        #        intg = int(strgener[-2:])
        #    else:
        #        intg = 0
        #if strgcomp is not None and strgener is not None:
        #    if gdat.fitt.typemodlenerfitt == 'full':
        #        gmod.dictindxpara[nameparabase + 'comp%s' % strgener][int(strgcomp[-1]), intg] = gmod.cntr
        #    else:
        #        gmod.dictindxpara[nameparabase + 'comp%s' % strgener][int(strgcomp[-1]), 0] = gmod.cntr
        #elif strglmdk is not None and strgener is not None:
        #    if strglmdk == 'linr':
        #        intglmdk = 0
        #    if strglmdk == 'quad':
        #        intglmdk = 1
        #    gmod.dictindxpara[nameparabase + 'ener'][intglmdk, intg] = gmod.cntr
        #elif strgener is not None:
        #    gmod.dictindxpara[nameparabase + 'ener'][intg] = gmod.cntr
        #elif strgcomp is not None:
        #    gmod.dictindxpara[nameparabase + 'comp'][int(strgcomp[-1])] = gmod.cntr
        
        gmod.cntr += 1
    else:
        ## fixed parameters
        gmod.listnameparafullfixd += [nameparabasefinl]
    

def proc_modl(gdat, strgmodl, strgextn, r):
    
    gmod = getattr(gdat, strgmodl)

    # to be deleted
    #for name in gdat.fitt.listnameparafull:
    #    if hasattr(gdat.fitt, name):
    #        gdat.fitt.listnameparafullfixd.append(name)
    #    else:
    #        gdat.fitt.listnameparafullvari.append(name)
    
    if gdat.booldiag:
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if len(gdat.arrytser['bdtr'][b][p]) == 0:
                    print('')
                    print('')
                    print('')
                    print('bp')
                    print(bp)
                    raise Exception('')
        
    #gdat.timethis = gdat.arrytser['bdtr'][b][p][:, 0, 0]
    #gdat.rflxthis = gdat.arrytser['bdtr'][b][p][:, :, 1]
    #gdat.stdvrflxthis = gdat.arrytser['bdtr'][b][p][:, :, 2]
    #gdat.varirflxthis = gdat.stdvrflxthis**2


    gmod.listminmpara = np.array(gmod.listminmpara)
    gmod.listmaxmpara = np.array(gmod.listmaxmpara)

    print('gmod.listlablpara')
    print(gmod.listlablpara)
    gmod.listlablpara, _, _, _, _ = tdpy.retr_listlablscalpara(gdat.fitt.listnameparafull, gmod.listlablpara, booldiag=gdat.booldiag)
    gmod.listlablparatotl = tdpy.retr_labltotl(gmod.listlablpara)
    
    gdat.numbpara = len(gdat.fitt.listnameparafullvari)
    gdat.meanpara = np.empty(gdat.numbpara)
    gdat.stdvpara = np.empty(gdat.numbpara)
    
    gdat.bfitperi = 4.25 # [days]
    gdat.stdvperi = 1e-2 * gdat.bfitperi # [days]
    gdat.bfitduratran = 0.45 * 24. # [hours]
    gdat.stdvduratran = 1e-1 * gdat.bfitduratran # [hours]
    gdat.bfitamplslen = 0.14 # [relative]
    gdat.stdvamplslen = 1e-1 * gdat.bfitamplslen # [relative]
    
    #gmod.listlablpara = [['$R_s$', 'R$_{\odot}$'], ['$P$', 'days'], ['$M_c$', 'M$_{\odot}$'], ['$M_s$', 'M$_{\odot}$']]
    #gmod.listlablparaderi = [['$A$', ''], ['$D$', 'hours'], ['$a$', 'R$_{\odot}$'], ['$R_{Sch}$', 'R$_{\odot}$']]
    #gmod.listlablpara += [['$M$', '$M_E$'], ['$T_{0}$', 'BJD'], ['$P$', 'days']]
    #gmod.listminmpara = np.concatenate([gmod.listminmpara, np.array([ 10., minmtime,  50.])])
    #gmod.listmaxmpara = np.concatenate([gmod.listmaxmpara, np.array([1e4, maxmtime, 200.])])
    
    meangauspara = None
    stdvgauspara = None
    numbpara = len(gmod.listlablpara)
    indxpara = np.arange(numbpara)
    
    listscalpara = gmod.dictfeatpara['scal']
    
    gdat.thisstrgmodl = 'fitt'
    # run the sampler
    if gdat.typeinfe == 'samp':
        gdat.dictsamp = tdpy.samp(gdat, \
                             gdat.numbsampwalk, \
                             retr_llik_mile, \
                             gdat.fitt.listnameparafullvari, gmod.listlablpara, listscalpara, gmod.listminmpara, gmod.listmaxmpara, \
                             pathbase=gdat.pathtargruns, \
                             retr_dictderi=retr_dictderi_mile, \
                             numbsampburnwalk=gdat.numbsampburnwalk, \
                             strgextn=strgextn, \
                             typeverb=gdat.typeverb, \
                             boolplot=gdat.boolplot, \
                            )
        
        gdat.numbsamp = gdat.dictsamp['lpos'].size
        gdat.indxsamp = np.arange(gdat.numbsamp)
        gdat.numbsampplot = min(10, gdat.numbsamp)
            
    if gdat.typeinfe == 'opti':
        
        bounds = [[] for kk in range(gmod.listminmpara.size)]
        print('bounds')
        for kk in range(gmod.listminmpara.size):
            bounds[kk] = [gmod.listminmpara[kk], gmod.listmaxmpara[kk]]
            print('%s %s: %g %g' % (gdat.fitt.listnameparafullvari[kk], gmod.listlablpara[kk], gmod.listminmpara[kk], gmod.listmaxmpara[kk]))
        print('')
            
        indx = np.where(gdat.liststrgdataitermlikdone == gdat.liststrgdataiter[gdat.indxdataiterthis[0]])[0]
        if indx.size == 1:
            print('Reading from the stored solution...')
            paramlik = gdat.datamlik[indx[0]][np.arange(0, 2 * gmod.listminmpara.size - 1, 2)]
            stdvmlik = gdat.datamlik[indx[0]][np.arange(0, 2 * gmod.listminmpara.size - 1, 2) + 1]
        else:

            gdat.parainit = gmod.listminmpara + 0.5 * (gmod.listmaxmpara - gmod.listminmpara)
            
            print('gdat.parainit')
            for kk in range(gmod.listminmpara.size):
                print('%s %s: %g' % (gdat.fitt.listnameparafullvari[kk], gmod.listlablpara[kk], gdat.parainit[kk]))
            print('')
            
            print('Maximizing the likelihood...')
            # minimize the negative loglikelihood
            objtmini = scipy.optimize.minimize(retr_lliknega_mile, gdat.parainit, \
                                                                            method='Nelder-Mead', \
                                                                            #method='BFGS', \
                                                                            #method='L-BFGS-B', \
                                                                            #ftol=0.1, \
                                                                            options={ \
                                                                            #"initial_simplex": simplex,
                                                                                        "disp": True, \
                                                                                        "maxiter" : gdat.parainit.size*200,
                                                                                        "fatol": 0.2, \
                                                                                        "adaptive": True, \
                                                                                        }, \
                                                                                          bounds=bounds, args=(gdat))
            
            paramlik = objtmini.x
            print('objtmini.success')
            print(objtmini.success)
            print(objtmini.status)
            print(objtmini.message)
            #print(objtmini.hess)
            print()
            gdat.indxpara = np.arange(paramlik.size)
            #stdvmlik = objtmini.hess_inv[gdat.indxpara, gdat.indxpara]
            stdvmlik = np.empty_like(paramlik)
            deltpara = 1e-6
            for kk in gdat.indxpara:
                paranewwfrst = np.copy(paramlik)
                paranewwfrst[kk] = (1 - deltpara) * paranewwfrst[kk]
                paranewwseco = np.copy(paramlik)
                paranewwseco[kk] = (1 + deltpara) * paranewwseco[kk]
                stdvmlik[kk] = 1. / np.sqrt(abs(retr_lliknega_mile(paranewwfrst, gdat) + retr_lliknega_mile(paranewwseco, gdat) \
                                                                             - 2. * retr_lliknega_mile(paramlik, gdat)) / (deltpara * paramlik[kk])**2)

            path = gdat.pathdatatarg + 'paramlik.csv'
            if gdat.typeverb > 0:
                print('Writing to %s...' % path)
            objtfile = open(path, 'a+')
            objtfile.write('%s' % gdat.liststrgdataiter[gdat.indxdataiterthis[0]])
            for kk, paramliktemp in enumerate(paramlik):
                objtfile.write(', %g, %g' % (paramliktemp, stdvmlik[kk]))
            objtfile.write('\n')
            objtfile.close()
        
        print('paramlik')
        for kk in range(gmod.listminmpara.size):
            print('%s %s: %g +- %g' % (gdat.fitt.listnameparafullvari[kk], gmod.listlablpara[kk], paramlik[kk], stdvmlik[kk]))
        
        gdat.dictmlik = dict()
        for kk in range(gmod.listminmpara.size):
            gdat.dictmlik[gdat.fitt.listnameparafullvari[kk]] = paramlik[kk]
            gdat.dictmlik['stdv' + gdat.fitt.listnameparafullvari[kk]] = stdvmlik[kk]
        print('Computing derived variables...')
        dictderimlik = retr_dictderi_mile(paramlik, gdat)
        for name in dictderimlik:
            gdat.dictmlik[name] = dictderimlik[name]
                
    if gdat.fitt.typemodlenerfitt == 'iter':
        if gdat.typeinfe == 'samp':
            gmod.listdictsamp.append(gdat.dictsamp)
        if gdat.typeinfe == 'opti':
            gmod.listdictmlik.append(gdat.dictmlik)

    if gdat.boolplottser:
        if ee < 10:
        
            #timedata = gdat.timethisfitt
            #lcurdata = gdat.rflxthisfitt[:, e]
                
            for b in gdat.indxdatatser:
                #plot_modl(gdat, strgmodl, b, None, None, e)
                for p in gdat.indxinst[b]:
                    #plot_modl(gdat, strgmodl, b, p, None, e)
                    for y in gdat.indxchun[b][p]:
                        plot_modl(gdat, strgmodl, b, p, y, e)


def plot_modl(gdat, strgmodl, b, p, y, e):
    
    gmod = getattr(gdat, strgmodl)
            
    if p is None:
        time = gdat.timethisfittconc[b]
        timefine = gdat.timethisfittfineconc[b]
    else:
        time = gdat.timethisfitt[b][p]
        timefine = gdat.timethisfittfine[b][p]
        tser = gdat.rflxthisfitt[b][p]
    
    strg = 'b%03dp%03d' % (b, p)
    
    # plot the data with the posterior median model
    strgextn = 'pmed%s%s' % (gdat.strgcnfg, gdat.liststrgdataiter[e])
    dictmodl = dict()
    for namecompmodl in gmod.listnamecompmodl:
        namecompmodlextn = 'modlfine%s%s' % (namecompmodl, strg)
        if gdat.typeinfe == 'samp':
            if gdat.fitt.typemodlenerfitt == 'full':
                lcurtemp = np.median(gdat.dictsamp[namecompmodlextn][:, :, e], 0)
            else:
                lcurtemp = np.median(gmod.listdictsamp[e][namecompmodlextn][:, :, 0], 0)
            strgtitl = 'Posterior median model'
        else:
            if gdat.fitt.typemodlenerfitt == 'full':
                lcurtemp = gdat.dictmlik[namecompmodlextn][:, e]
            else:
                lcurtemp = gmod.listdictmlik[e][namecompmodlextn][:, 0]
        if namecompmodl == 'totl':
            colr = 'b'
            labl = 'Total Model'
        elif namecompmodl == 'sgnl':
            colr = 'g'
            labl = 'Signal'
        elif namecompmodl == 'blin':
            colr = 'orange'
            labl = 'Baseline'
        elif namecompmodl == 'tran':
            colr = 'r'
            labl = 'Transit'
        elif namecompmodl == 'supn':
            colr = 'm'
            labl = 'Supernova'
        elif namecompmodl == 'excs':
            colr = 'olive'
            labl = 'Excess'
        else:
            print('')
            print('namecompmodl')
            print(namecompmodl)
            raise Exception('')
        dictmodl['pmed' + namecompmodlextn] = {'lcur': lcurtemp, 'time': timefine, 'labl': labl, 'colr': colr}
    
    if p is not None and gdat.listlablinst[b][p] != '':
        strglablinst = ', %s' % gdat.listlablinst[b][p]
    else:
        strglablinst = ''
    
    print('')
    print('')
    print('')
    print('')
    print('')
    print('')
    print('')
    print('')
    print('strglablinst')
    print(strglablinst)
    print('gdat.listlablinst[b][p]')
    print(gdat.listlablinst[b][p])
    print('')
    print('')
    print('')
    print('')
    print('')
    print('')
    print('')
    raise Exception('')

    if gdat.lablcnfg != '':
        lablcnfgtemp = ', %s' % gdat.lablcnfg
    else:
        lablcnfgtemp = ''

    if e == 0 and gdat.numbener[p] == 1:
        strgtitl = '%s%s%s' % (gdat.labltarg, strglablinst, lablcnfgtemp)
    elif e == 0 and gdat.numbener[p] > 1:
        strgtitl = '%s%s%s, white' % (gdat.labltarg, strglablinst, lablcnfgtemp)
    else:
        strgtitl = '%s%s%s, %g micron' % (gdat.labltarg, strglablinst, lablcnfgtemp, gdat.listener[p][e-1])
    
    pathplot = ephesos.plot_lcur(gdat.pathvisutarg, \
                                 timedata=time, \
                                 lcurdata=tser, \
                                 timeoffs=gdat.timeoffs, \
                                 strgextn=strgextn, \
                                 strgtitl=strgtitl, \
                                 boolwritover=gdat.boolwritover, \
                                 boolbrekmodl=gdat.boolbrekmodl, \
                                 dictmodl=dictmodl)
    
    # plot the posterior median residual
    strgextn = 'resipmed%s%s' % (gdat.strgcnfg, gdat.liststrgdataiter[e])
    if gdat.typeinfe == 'samp':
        if gdat.fitt.typemodlenerfitt == 'full':
            lcurdatatemp = np.median(gdat.dictsamp['resi%s' % strg][:, :, e], 0)
        else:
            lcurdatatemp = np.median(gmod.listdictsamp[e]['resi%s' % strg][:, :, 0], 0)
    else:
        if gdat.fitt.typemodlenerfitt == 'full':
            lcurdatatemp = gdat.dictmlik['resi%s' % strg][:, e]
        else:
            lcurdatatemp = gmod.listdictmlik[e]['resi%s' % strg][:, 0]
    pathplot = ephesos.plot_lcur(gdat.pathvisutarg, \
                                 timedata=time, \
                                 lcurdata=lcurdatatemp, \
                                 timeoffs=gdat.timeoffs, \
                                 strgextn=strgextn, \
                                 strgtitl=strgtitl, \
                                 lablyaxi='Residual relative flux', \
                                 boolwritover=gdat.boolwritover, \
                                 boolbrekmodl=gdat.boolbrekmodl, \
                                )
    
    # plot the data with a number of total model samples
    if gdat.typeinfe == 'samp':
        strgextn = 'psam%s' % gdat.strgcnfg
        if gdat.numbener[p] > 1:
            strgextn += gdat.liststrgdataiter[e]
        dictmodl = dict()
        for w in range(gdat.numbsampplot):
            namevarbsamp = 'psammodl%04d' % w
            if gdat.fitt.typemodlenerfitt == 'full':
                dictmodl[namevarbsamp] = {'lcur': gdat.dictsamp['modlfinetotl%s' % strg][w, :, e], 'time': timefine}
            else:
                dictmodl[namevarbsamp] = {'lcur': gmod.listdictsamp[e]['modlfinetotl%s' % strg][w, :, 0], 'time': timefine}
            
            if gdat.booldiag:
                if dictmodl[namevarbsamp]['lcur'].size != dictmodl[namevarbsamp]['time'].size:
                    print('')
                    print('strg')
                    print(strg)
                    print('dictmodl[namevarbsamp][lcur]')
                    summgene(dictmodl[namevarbsamp]['lcur'])
                    print('dictmodl[namevarbsamp][time]')
                    summgene(dictmodl[namevarbsamp]['time'])
                    raise Exception('')

            if w == 0:
                dictmodl[namevarbsamp]['labl'] = 'Model'
            else:
                dictmodl[namevarbsamp]['labl'] = None
            dictmodl[namevarbsamp]['colr'] = 'b'
            dictmodl[namevarbsamp]['alph'] = 0.2
        pathplot = ephesos.plot_lcur(gdat.pathvisutarg, \
                                     timedata=gdat.timethisfitt[b][p], \
                                     lcurdata=gdat.rflxthisfitt[b][p], \
                                     timeoffs=gdat.timeoffs, \
                                     strgextn=strgextn, \
                                     boolwritover=gdat.boolwritover, \
                                     strgtitl=strgtitl, \
                                     boolbrekmodl=gdat.boolbrekmodl, \
                                     dictmodl=dictmodl)

        # plot the data with a number of model component samples
        strgextn = 'psamcomp%s' % gdat.strgcnfg
        if gdat.numbener[p] > 1:
            strgextn += gdat.liststrgdataiter[e]
        dictmodl = dict()
        for namecompmodl in gdat.fitt.listnamecompmodl:
            if namecompmodl == 'totl':
                continue

            if namecompmodl == 'totl':
                colr = 'b'
                labl = 'Total Model'
            elif namecompmodl == 'blin':
                colr = 'g'
                labl = 'Baseline'
            elif namecompmodl == 'supn':
                colr = 'r'
                labl = 'Supernova'
            elif namecompmodl == 'excs':
                colr = 'orange'
                labl = 'Excess'
            elif namecompmodl == 'sgnl':
                colr = 'b'
                labl = 'Signal'
            else:
                print('')
                print('namecompmodl')
                print(namecompmodl)
                raise Exception('')

            for w in range(gdat.numbsampplot):
                namevarbsamp = 'psam%s%04d' % (namecompmodl, w)
                if gdat.fitt.typemodlenerfitt == 'full':
                    dictmodl[namevarbsamp] = {'lcur': gdat.dictsamp['modlfine%s%s' % (namecompmodl, strg)][w, :, e], 'time': gdat.timethisfittfine[b][p]}
                else:
                    dictmodl[namevarbsamp] = \
                                {'lcur': gmod.listdictsamp[e]['modlfine%s%s' % (namecompmodl, strg)][w, :, 0], 'time': gdat.timethisfittfine[b][p]}
                if w == 0:
                    dictmodl[namevarbsamp]['labl'] = labl
                else:
                    dictmodl[namevarbsamp]['labl'] = None
                dictmodl[namevarbsamp]['colr'] = colr
                dictmodl[namevarbsamp]['alph'] = 0.6
        pathplot = ephesos.plot_lcur(gdat.pathvisutarg, \
                                     timedata=gdat.timethisfitt[b][p], \
                                     timeoffs=gdat.timeoffs, \
                                     lcurdata=gdat.rflxthisfitt[b][p], \
                                     strgextn=strgextn, \
                                     boolwritover=gdat.boolwritover, \
                                     strgtitl=strgtitl, \
                                     boolbrekmodl=gdat.boolbrekmodl, \
                                     dictmodl=dictmodl)

    # plot the binned RMS
    path = gdat.pathvisutarg + 'stdvrebn%s%s.%s' % (gdat.strgcnfg, gdat.liststrgdataiter[e], gdat.typefileplot)
    if not os.path.exists(path):
        if gdat.typeinfe == 'samp':
            if gdat.fitt.typemodlenerfitt == 'full':
                stdvresi = np.median(gdat.dictsamp['stdvresi%s' % strg][:, :, e], 0)
            else:
                stdvresi = np.median(gmod.listdictsamp[e]['stdvresi%s' % strg][:, :, 0], 0)
        else:
            if gdat.fitt.typemodlenerfitt == 'full':
                stdvresi = gdat.dictmlik['stdvresi%s' % strg][:, e]
            else:
                stdvresi = gmod.listdictmlik[e]['stdvresi' % strg][:, 0]
    
        figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
        axis.loglog(gdat.listdeltrebn[b][p] * 24., stdvresi * 1e6, ls='', marker='o', ms=1, label='Binned Std. Dev')
        axis.axvline(gdat.cadetime[b][p] * 24., ls='--', label='Sampling rate')
        axis.set_ylabel('RMS [ppm]')
        axis.set_xlabel('Bin width [hour]')
        axis.legend()
        plt.tight_layout()
        if gdat.typeverb > 0:
            print('Writing to %s...' % path)
        plt.savefig(path)
        plt.close()
        

def setp_modlinit(gdat, strgmodl):
    '''
    Set up the modeling variables common to all models
    '''
    gmod = getattr(gdat, strgmodl)
    
    print('Performing initial setup for model %s...' % strgmodl)
    gmod.boolmodlcosc = gmod.typemodl == 'cosc'
    
    print('gmod.boolmodlcosc')
    print(gmod.boolmodlcosc)
    
    gmod.boolmodlpsys = gmod.typemodl == 'psys' or gmod.typemodl == 'psyspcur' or gmod.typemodl == 'psysttvr'
    
    if gdat.typeverb > 0:
        print('gmod.boolmodlpsys')
        print(gmod.boolmodlpsys)
    
    gmod.boolmodltran = gmod.boolmodlpsys or gmod.boolmodlcosc
    
    print('gmod.boolmodltran')
    print(gmod.boolmodltran)
        
    gmod.boolmodlpcur = gmod.typemodl == 'pcur' or gmod.typemodl == 'psyspcur'
    
    print('gmod.boolmodlpcur')
    print(gmod.boolmodlpcur)
    
    if gmod.typemodl == 'supn':
        # 'linr': quadratic
        # 'quad': quadratic
        # 'cubc': cubic
        # 'gpro': GP process
        tdpy.setp_para_defa(gdat, strgmodl, 'typemodlsupn', 'quad')
        
        # 'none': No excess
        # 'bump': single bump
        tdpy.setp_para_defa(gdat, strgmodl, 'typemodlexcs', 'bump')

    gmod.listnameparafullfixd = []
    gmod.listnameparafullvari = []

    # type of baseline shape
    tdpy.setp_para_defa(gdat, strgmodl, 'typemodlblinshap', 'cons')
    
    # type of baseline energy dependence
    typemodlblinener = ['cons' for p in gdat.indxinst[0]]
    for p in gdat.indxinst[0]:
        tdpy.setp_para_defa(gdat, strgmodl, 'typemodlblinener', typemodlblinener)
    

# this will likely be merged with setp_modlbase()
def init_modl(gdat, strgmodl):
    
    gmod = getattr(gdat, strgmodl)
    
    gmod.dictindxpara = dict()
    gmod.dictfeatpara = dict()
    gmod.dictfeatpara['scal'] = []
    
    gmod.listlablpara = []
    gmod.listminmpara = []
    gmod.listmaxmpara = []
    gmod.listnameparafull = []
            
    # counter for the parameter index
    gmod.cntr = 0


def setp_modlbase(gdat, strgmodl, r=None):
    
    print('')
    print('Setting up the model (%s) by running setp_modlbase()...' % strgmodl)
    
    gmod = getattr(gdat, strgmodl)
    
    print('gmod.typemodl')
    print(gmod.typemodl)

    gmod.boolmodlcomp = 'psys' in gmod.typemodl
            
    tdpy.setp_para_defa(gdat, strgmodl, 'typemodllmdkener', 'cons')
    tdpy.setp_para_defa(gdat, strgmodl, 'typemodllmdkterm', 'quad')
    
    if gdat.typeverb > 0:
        print('gmod.typemodllmdkener')
        print(gmod.typemodllmdkener)
        print('gmod.typemodllmdkterm')
        print(gmod.typemodllmdkterm)

    gmod.listnamecompmodl = ['sgnl', 'blin']
    #if gmod.typemodl == 'flar':
    #    gmod.listnamecompmodl += ['flar']
    if gmod.typemodl == 'cosc' or gmod.typemodl == 'psys' or gmod.typemodl == 'psyspcur' or gmod.typemodl == 'psysttvr':
        gmod.listnamecompmodl += ['tran']

        if gmod.boolmodltran:
            gmod.numbcomp = gdat.epocmtracompprio.size
        else:
            gmod.numbcomp = 0
        
        if gdat.typeverb > 0:
            print('gmod.numbcomp')
            print(gmod.numbcomp)
        
        gmod.indxcomp = np.arange(gmod.numbcomp)
     
    if gmod.typemodl.startswith('psys') or gmod.typemodl == 'cosc':
        # number of terms in the LD law
        if gmod.typemodllmdkterm == 'line':
            gmod.numbcoeflmdkterm = 1
        if gmod.typemodllmdkterm == 'quad':
            gmod.numbcoeflmdkterm = 2
        
        # number of distinct coefficients for each term in the LD law
        if gmod.typemodllmdkener == 'ener':
            gmod.numbcoeflmdkener = gdat.numbener[p]
        else:
            gmod.numbcoeflmdkener = 1
            
    gdat.listnamecompgpro = ['totl']
    if gmod.typemodlblinshap == 'gpro':
        gdat.listnamecompgpro.append('blin')
    
    if gmod.typemodl == 'supn':
        gmod.listnamecompmodl += ['supn']
        if gmod.typemodlexcs != 'none':
            gmod.listnamecompmodl += ['excs']
    
    if len(gmod.listnamecompmodl) > 1:
        gmod.listnamecompmodl += ['totl']
    
    # baseline
    for p in gdat.indxinst[0]:
        if gmod.typemodlblinshap == 'gpro':
            gmod.listnameparabase = ['sigmgprobase', 'rhoogprobase']
        if gmod.typemodlblinshap == 'cons':
            if gdat.numbener[p] > 1 and gmod.typemodlblinener[p] == 'ener':
                gmod.listnameparabase = []
                for e in gdat.indxener[p]:
                    gmod.listnameparabase += ['consblinener%04d' % e]
            else:
                gmod.listnameparabase = ['consblin']
        if gmod.typemodlblinshap == 'step':
            gmod.listnameparabase = ['consblinfrst', 'consblinseco', 'timestep', 'scalstep']
    

    print('gmod.listnameparabase')
    print(gmod.listnameparabase)
    
    for nameparabase in gmod.listnameparabase:
        
        # collect group of parameters
        #gmod.dictindxpara[nameparabase + 'ener'] = np.empty(gdat.numbenerthismodl, dtype=int)
        
        if nameparabase.startswith('sigmgprobase'):
            minmpara = 0.01 # [ppt]
            maxmpara = 4. # [ppt]
            lablpara = ['$\sigma_{GP}$', '']
        if nameparabase.startswith('rhoogprobase'):
            minmpara = 1e-3
            maxmpara = 0.3
            lablpara = [r'$\rho_{GP}$', '']
        if nameparabase.startswith('consblin'):
            if nameparabase == 'consblinfrst':
                lablpara = ['$C_1$', 'ppt']
                minmpara = -20. # [ppt]
                maxmpara = 20. # [ppt]
            elif nameparabase == 'consblinseco':
                lablpara = ['$C_2$', 'ppt']
                minmpara = -20. # [ppt]
                maxmpara = -4. # [ppt]
            else:
                lablpara = ['$C$', 'ppt']
                minmpara = -20. # [ppt]
                maxmpara = 20. # [ppt]
        if nameparabase.startswith('timestep'):
            minmpara = 791.11
            maxmpara = 791.13
            lablpara = '$T_s$'
        if nameparabase.startswith('scalstep'):
            minmpara = 0.0001
            maxmpara = 0.002
            lablpara = '$A_s$'

        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                setp_para(gdat, strgmodl, nameparabase, minmpara, maxmpara, lablpara)
        
    gmod.listindxdatainsteneriter = []
    for b in gdat.indxdatatser:
        for p in gdat.indxinst[b]:
            if strgmodl == 'true':
                gmod.listindxdatainsteneriter.append([b, p, gdat.indxener])
            else:
                if gdat.fitt.typemodlenerfitt == 'full':
                    gmod.listindxdatainsteneriter.append([b, p, gdat.indxener])
                else:
                    for e in gdat.indxener[p]:
                        gmod.listindxdatainsteneriter.append([np.array([e])])
        
    tdpy.setp_para_defa(gdat, strgmodl, 'timestep', 791.12)
    tdpy.setp_para_defa(gdat, strgmodl, 'scalstep', 0.00125147)
                        
    if gmod.typemodl == 'flar':
        setp_para(gdat, strgmodl, 'numbflar', 0, 10, ['$N_f$', ''], boolvari=False)
        
        # fixed parameters of the fitting model
        if strgmodl == 'fitt':
            tdpy.setp_para_defa(gdat, strgmodl, 'numbflar', 1)
        
        gmod.indxflar = np.arange(gmod.numbflar)
        for k in gmod.indxflar:
            setp_para(gdat, strgmodl, 'amplflar%04d' % k, 0., 0.15, ['$A_{%d}$' % k, ''])
            setp_para(gdat, strgmodl, 'tsclflar%04d' % k, 0., 12., ['$t_{s,%d}$' % k, 'hour'])
            setp_para(gdat, strgmodl, 'timeflar%04d' % k, 0., 0.15, ['$t_{f,%d}$' % k, 'day'])

    if strgmodl == 'true':
        if gmod.typemodl.startswith('psys') or gmod.typemodl == 'cosc':
            if gdat.true.typemodllmdkener == 'linr':
                pass
            elif gdat.true.typemodllmdkener == 'cons':
                print('dsmlsvkvs fsvs')
                tdpy.setp_para_defa(gdat, 'true', 'coeflmdklinr', 0.4)
                tdpy.setp_para_defa(gdat, 'true', 'coeflmdkquad', 0.25)
            elif gdat.true.typemodllmdkener == 'ener':
                tdpy.setp_para_defa(gdat, 'true', 'coeflmdklinrwhit', 0.4)
                tdpy.setp_para_defa(gdat, 'true', 'coeflmdkquadwhit', 0.25)
                for p in gdat.indxinst[0]:
                    tdpy.setp_para_defa(gdat, 'true', 'coeflmdklinr' % strginst, 0.4)
                    tdpy.setp_para_defa(gdat, 'true', 'coeflmdkquad' % strginst, 0.25)
            
    if gmod.typemodl == 'psys' or gmod.typemodl == 'cosc' or gmod.typemodl == 'psysttvr' or gmod.typemodl == 'psyspcur':
        
        #gmod.listnameparasyst = []

        # list of companion parameter names
        gmod.listnameparacomp = [[] for j in gmod.indxcomp]
        for j in gmod.indxcomp:
            if gmod.typemodl == 'psysttvr':
                if gmod.typemodlttvr == 'indilineflot' or gmod.typemodlttvr == 'globlineflot':
                    gmod.listnameparacomp[j] += ['peri', 'epocmtra']
                if gmod.typemodlttvr == 'globlineuser' or gmod.typemodlttvr == 'globlineflot':
                    for lll in range(gdat.numbtran[j]):
                        gmod.listnameparacomp[j] += ['ttvr%04d' % lll]
            if gmod.typemodl == 'cosc':
                gmod.listnameparacomp[j] += ['mass']
            if not (gmod.typemodl == 'psysttvr' and gmod.typemodlttvr == 'indilineuser'):
                gmod.listnameparacomp[j] += ['rrat']
                gmod.listnameparacomp[j] += ['rsma', 'peri', 'epocmtra', 'cosi']
    
        print('gmod.listnameparacomp')
        print(gmod.listnameparacomp)
    
        # define arrays of parameter indices for companions
        for namepara in gmod.listnameparacomp[0]:
            boolgood = True
            for jj in gmod.indxcomp:
                if not namepara in gmod.listnameparacomp[jj]:
                    boolgood = False
            if boolgood:
                pass
                if gdat.numbener[p] > 1:
                    gmod.dictindxpara[namepara + 'comp'] = np.empty(gmod.numbcomp, dtype=int)

                if gdat.numbener[p] > 1 and gdat.fitt.typemodlenerfitt == 'full':
                    gmod.dictindxpara['rratcompener'] = np.empty((gmod.numbcomp, gdat.numbener[p]), dtype=int)
    
        # limb darkening
        if gmod.typemodllmdkterm != 'none':
            if gmod.typemodllmdkener == 'ener' and gdat.fitt.typemodlenerfitt == 'full':
                gmod.dictindxpara['coeflmdkener'] = np.empty((gmod.numbcoeflmdkterm, gmod.numbcoeflmdkener), dtype=int)
            else:
                gmod.dictindxpara['coeflmdkener'] = np.empty((gmod.numbcoeflmdkterm, 1), dtype=int)
        
            #gmod.dictindxpara['coeflmdklinrener'] = np.empty(1, dtype=int)
            #gmod.dictindxpara['coeflmdkquadener'] = np.empty(1, dtype=int)
            
            print('setp_para calls relevant to coeflmdk...')

            if gdat.numbener[p] > 1:
                if gmod.typemodllmdkener == 'cons':
                    setp_para(gdat, strgmodl, 'coeflmdklinr', 0., 1., None)
                    setp_para(gdat, strgmodl, 'coeflmdkquad', 0., 1., None)
                elif gdat.fitt.typemodlenerfitt == 'full':
                    for e in gdat.indxener[p]:
                        #setattr(gmod, 'coeflmdklinr' + gdat.liststrgener[p][e], 0.2)
                        #setattr(gmod, 'coeflmdkquad' + gdat.liststrgener[p][e], 0.4)
                        setp_para(gdat, strgmodl, 'coeflmdklinr', 0., 1., None, strgener=gdat.liststrgener[p][e])
                else:
                    
                    if gmod.typemodllmdkener == 'cons':
                        raise Exception('')
                    #or gmod.typemodllmdkener == 'ener':
                    #    
                    #    strgener = gdat.liststrgdataiter[e]
                    #    
                    #    if gmod.typemodllmdkterm != 'none':
                    #        # add linear coefficient
                    #        setp_para(gdat, strgmodl, 'coeflmdklinr%s' % strgener, 0., 0.15, '$u_{1,%d}$' % e)
                    #        
                    #    if gmod.typemodllmdkterm == 'quad':
                    #        # add quadratic coefficient
                    #        setp_para(gdat, strgmodl, 'coeflmdkquad%s' % strgener, 0., 0.3, '$u_{2,%d}$' % e)
                        pass
                    elif gmod.typemodllmdkener == 'line':
                        if gmod.typemodllmdkterm != 'none':
                            setp_para(gdat, strgmodl, 'ratecoeflmdklinr', 0., 1., None)
                        
                        if gmod.typemodllmdkterm == 'quad':
                            setp_para(gdat, strgmodl, 'ratecoeflmdkquad', 0., 1., None)
                    else:
                        raise Exception('')
                
                #raise Exception('')
        
        for j in gmod.indxcomp:
            
            # define parameter limits
            if gmod.typemodl == 'cosc':
                setp_para(gdat, strgmodl, 'radistar', 0.1, 100., ['$R_*$', ''])
                setp_para(gdat, strgmodl, 'massstar', 0.1, 100., ['$M_*$', ''])
            
            strgcomp = 'com%d' % j
            
            setp_para(gdat, strgmodl, 'rsma', 0.06, 0.14, None, strgcomp=strgcomp)
            setp_para(gdat, strgmodl, 'peri', gdat.pericompprio[j] - 0.01 * gdat.pericompprio[j], \
                                                    gdat.pericompprio[j] + 0.01 * gdat.pericompprio[j], None, strgcomp=strgcomp)
            
            setp_para(gdat, strgmodl, 'epocmtra', np.amin(gdat.timeconc[0]), np.amax(gdat.timeconc[0]), None, strgcomp=strgcomp)
            setp_para(gdat, strgmodl, 'cosi', 0., 0.08, None, strgcomp=strgcomp)
            
            minmpara = 0.11
            maxmpara = 0.19
            if gdat.numbener[p] > 1 and (strgmodl == 'true' or gdat.fitt.typemodlenerfitt == 'full'):
                for e in gdat.indxener[p]:
                    setp_para(gdat, strgmodl, 'rrat', minmpara, maxmpara, None, strgener=gdat.liststrgener[p][e], strgcomp=strgcomp)
            else:
                setp_para(gdat, strgmodl, 'rrat', minmpara, maxmpara, None, strgcomp=strgcomp)
            
            if gmod.typemodl == 'cosc':
                setp_para(gdat, strgmodl, 'mass', 0.1, 100., ['$M_c$', ''], strgcomp=strgcomp)

    if gmod.typemodl == 'supn':
        # temp
        if gdat.liststrgtypedata[0][0].startswith('simu'):
            minmtimesupn = gdat.minmtimethis + 0.15 * (gdat.maxmtimethis - gdat.minmtimethis) - gdat.timeoffs
            maxmtimesupn = gdat.minmtimethis + 0.35 * (gdat.maxmtimethis - gdat.minmtimethis) - gdat.timeoffs
        else:
            minmtimesupn = 358.
            maxmtimesupn = 363.
        
        lablpara = ['$T_0$', 'BJD-%d' % gdat.timeoffs]
        setp_para(gdat, strgmodl, 'timesupn', minmtimesupn, maxmtimesupn, lablpara)
        
        if gmod.typemodlexcs == 'bump':
            setp_para(gdat, strgmodl, 'timebumpoffs', 0., 1., ['$T_b$', ''])
            setp_para(gdat, strgmodl, 'amplbump', 0., 50., [r'$A_b$', '']) # [ppt]
            setp_para(gdat, strgmodl, 'scalbump', 0.01, 0.5, [r'$u_b$', ''])
        
        setp_para(gdat, strgmodl, 'coeflinesupn', -20., 50., ['$c_1$', 'ppt'])
        if gmod.typemodlsupn == 'quad':
            setp_para(gdat, strgmodl, 'coefquadsupn', -20., 50., ['$c_2$', 'ppt'])

    if gmod.boolmodltran:
        booltrancomp = np.zeros(gmod.numbcomp, dtype=bool)
        booltrancomp[np.where(np.isfinite(gdat.duraprio))] = True
        tdpy.setp_para_defa(gdat, strgmodl, 'booltrancomp', booltrancomp)

    print('gmod.listnameparafull')
    print(gmod.listnameparafull)
    print('gmod.listnameparafullfixd')
    print(gmod.listnameparafullfixd)
    print('gmod.listnameparafullvari')
    print(gmod.listnameparafullvari)
    print('gmod.dictindxpara')
    if gdat.booldiag:
        for strgtemp, valutemp in gmod.dictindxpara.items():
            print(strgtemp)
            print(valutemp)


def exec_lspe(arrylcur, pathvisu=None, pathdata=None, strgextn='', factnyqt=None, \
              
              # minimum frequency (1/days)
              minmfreq=None, \
              # maximum frequency (1/days)
              maxmfreq=None, \
              
              factosam=3., \

              # factor to scale the size of text in the figures
              factsizetextfigr=1., \

              ## file type of the plot
              typefileplot='png', \
              
              # verbosity level
              typeverb=0, \
             
             ):
    '''
    Calculate the LS periodogram of a time-series.
    '''
    
    if maxmfreq is not None and factnyqt is not None:
        raise Exception('')
    
    dictlspeoutp = dict()
    
    if pathvisu is not None:
        pathplot = pathvisu + 'LSPeriodogram_%s.%s' % (strgextn, typefileplot)

    if pathdata is not None:
        pathcsvv = pathdata + 'LSPeriodogram_%s.csv' % strgextn
    
    if pathdata is None or not os.path.exists(pathcsvv) or pathvisu is not None and not os.path.exists(pathplot):
        print('Calculating LS periodogram...')
        
        # factor by which the maximum frequency is compared to the Nyquist frequency
        if factnyqt is None:
            factnyqt = 1.
        
        time = arrylcur[:, 0]
        lcur = arrylcur[:, 1]
        numbtime = time.size
        minmtime = np.amin(time)
        maxmtime = np.amax(time)
        delttime = maxmtime - minmtime
        freqnyqt = numbtime / delttime / 2.
        
        if minmfreq is None:
            minmfreq = 1. / delttime
        
        if maxmfreq is None:
            maxmfreq = factnyqt * freqnyqt
        
        # determine the frequency sampling resolution with N samples per line
        deltfreq = minmfreq / factosam / 2.
        freq = np.arange(minmfreq, maxmfreq, deltfreq)
        peri = 1. / freq
        
        objtlspe = astropy.timeseries.LombScargle(time, lcur, nterms=1)

        powr = objtlspe.power(freq)
        
        if pathdata is not None:
            arry = np.empty((peri.size, 2))
            arry[:, 0] = peri
            arry[:, 1] = powr
            print('Writing to %s...' % pathcsvv)
            np.savetxt(pathcsvv, arry, delimiter=',')
    
    else:
        if typeverb > 0:
            print('Reading from %s...' % pathcsvv)
        arry = np.loadtxt(pathcsvv, delimiter=',')
        peri = arry[:, 0]
        powr = arry[:, 1]
    
    #listindxperipeak, _ = scipy.signal.find_peaks(powr)
    #indxperimpow = listindxperipeak[0]
    indxperimpow = np.argmax(powr)
    
    perimpow = peri[indxperimpow]
    powrmpow = powr[indxperimpow]

    if pathvisu is not None:
        if not os.path.exists(pathplot):
            
            sizefigr = np.array([7., 3.5])
            sizefigr /= factsizetextfigr

            figr, axis = plt.subplots(figsize=sizefigr)
            axis.plot(peri, powr, color='k')
            
            axis.axvline(perimpow, alpha=0.4, lw=3)
            minmxaxi = np.amin(peri)
            maxmxaxi = np.amax(peri)
            for n in range(2, 10):
                xpos = n * perimpow
                if xpos > maxmxaxi:
                    break
                axis.axvline(xpos, alpha=0.4, lw=1, linestyle='dashed')
            for n in range(2, 10):
                xpos = perimpow / n
                if xpos < minmxaxi:
                    break
                axis.axvline(xpos, alpha=0.4, lw=1, linestyle='dashed')
            
            strgtitl = 'Maximum power of %.3g at %.3f days' % (powrmpow, perimpow)
            
            listprob = [0.05]
            powrfals = objtlspe.false_alarm_level(listprob)
            for p in range(len(listprob)):
                axis.axhline(powrfals[p], ls='--')

            axis.set_xscale('log')
            axis.set_xlabel('Period [days]')
            axis.set_ylabel('Normalized Power')
            axis.set_title(strgtitl)
            print('Writing to %s...' % pathplot)
            plt.savefig(pathplot)
            plt.close()
        dictlspeoutp['pathplot'] = pathplot

    dictlspeoutp['perimpow'] = perimpow
    dictlspeoutp['powrmpow'] = powrmpow
    
    return dictlspeoutp


@jit(nopython=True)
def srch_pbox_work_loop(m, phas, phasdiff, dydchalf):
    
    phasoffs = phas - phasdiff[m]
    
    if phasdiff[m] < dydchalf:
        booltemp = (phasoffs < dydchalf) | (1. - phas < dydchalf - phasoffs)
    elif 1. - phasdiff[m] < dydchalf:
        booltemp = (1. - phas - phasdiff[m] < dydchalf) | (phas < dydchalf - phasoffs)
    else:
        booltemp = np.abs(phasoffs) < dydchalf
    
    indxitra = np.where(booltemp)[0]
    
    return indxitra


def srch_pbox_work(listperi, listarrytser, listdcyc, listepoc, listduratrantotllevl, i):
    
    numbperi = len(listperi[i])
    numbdcyc = len(listdcyc[0])
    
    numblevlrebn = len(listduratrantotllevl)
    indxlevlrebn = np.arange(numblevlrebn)
    
    #conschi2 = np.sum(weig * arrytser[:, 1]**2)
    #listtermchi2 = np.empty(numbperi)
    
    rflxitraminm = np.zeros(numbperi) + 1e100
    dcycmaxm = np.zeros(numbperi)
    epocmaxm = np.zeros(numbperi)
    
    listphas = [[] for b in indxlevlrebn]
    for k in tqdm(range(len(listperi[i]))):
        
        peri = listperi[i][k]
        
        for b in indxlevlrebn:
            listphas[b] = (listarrytser[b][:, 0] % peri) / peri
        
        for l in range(len(listdcyc[k])):
            
            b = np.digitize(listdcyc[k][l] * peri * 24., listduratrantotllevl) - 1
            #b = 0
            
            #print('listduratrantotllevl')
            #print(listduratrantotllevl)
            #print('listdcyc[k][l] * peri * 24.')
            #print(listdcyc[k][l] * peri * 24.)
            #print('b')
            #print(b)

            dydchalf = listdcyc[k][l] / 2.

            phasdiff = (listepoc[k][l] % peri) / peri
            
            #print('listphas[b]')
            #summgene(listphas[b])
            #print('')
            
            for m in range(len(listepoc[k][l])):
                
                indxitra = srch_pbox_work_loop(m, listphas[b], phasdiff, dydchalf)
                
                if indxitra.size == 0:
                    continue
    
                rflxitra = np.mean(listarrytser[b][:, 1][indxitra])
                
                if rflxitra < rflxitraminm[k]:
                    rflxitraminm[k] = rflxitra
                    dcycmaxm[k] = listdcyc[k][l]
                    epocmaxm[k] = listepoc[k][l][m]
                
                if not np.isfinite(rflxitra):
                    print('b')
                    print(b)
                    print('listarrytser[b][:, 1]')
                    summgene(listarrytser[b][:, 1])
                    #print('depttrancomp')
                    #print(dept)
                    #print('np.std(rflx[indxitra])')
                    #summgene(np.std(rflx[indxitra]))
                    #print('rflx[indxitra]')
                    #summgene(rflx[indxitra])
                    raise Exception('')
                    
                #timechecloop[0][k, l, m] = timemodu.time()
                #print('pericomp')
                #print(peri)
                #print('dcyc')
                #print(dcyc)
                #print('epocmtracomp')
                #print(epoc)
                #print('phasdiff')
                #summgene(phasdiff)
                #print('phasoffs')
                #summgene(phasoffs)
                
                #print('booltemp')
                #summgene(booltemp)
                #print('indxitra')
                #summgene(indxitra)
                #print('depttrancomp')
                #print(dept)
                #print('stdv')
                #print(stdv)
                #terr = np.sum(weig[indxitra])
                #ters = np.sum(weig[indxitra] * rflx[indxitra])
                #termchi2 = ters**2 / terr / (1. - terr)
                #print('ters')
                #print(ters)
                #print('terr')
                #print(terr)
                #print('depttrancomp')
                #print(dept)
                #print('indxitra')
                #summgene(indxitra)
                #print('s2nr')
                #print(s2nr)
                #print('')
                
                #if True:
                if False:
                    figr, axis = plt.subplots(2, 1, figsize=(8, 8))
                    axis[0].plot(listarrytser[b][:, 0], listarrytser[b][:, 1], color='b', ls='', marker='o', rasterized=True, ms=0.3)
                    axis[0].plot(listarrytser[b][:, 0][indxitra], listarrytser[b][:, 1][indxitra], color='firebrick', ls='', marker='o', ms=2., rasterized=True)
                    axis[0].axhline(1., ls='-.', alpha=0.3, color='k')
                    axis[0].set_xlabel('Time [BJD]')
                    
                    axis[1].plot(listphas[b], listarrytser[b][:, 1], color='b', ls='', marker='o', rasterized=True, ms=0.3)
                    axis[1].plot(listphas[b][indxitra], listarrytser[b][:, 1][indxitra], color='firebrick', ls='', marker='o', ms=2., rasterized=True)
                    axis[1].plot(np.mean(listphas[b][indxitra]), rflxitra, color='g', ls='', marker='o', ms=4., rasterized=True)
                    axis[1].axhline(1., ls='-.', alpha=0.3, color='k')
                    axis[1].set_xlabel('Phase')
                    titl = '$P$=%.3f, $T_0$=%.3f, $q_{tr}$=%.3g, $f$=%.6g' % (peri, listepoc[k][l][m], listdcyc[k][l], rflxitra)
                    axis[0].set_title(titl, usetex=False)
                    path = '/Users/tdaylan/Documents/work/data/troia/toyy_tessprms2min_TESS/mock0001/imag/rflx_tria_diag_%04d%04d.pdf' % (l, m)
                    print('Writing to %s...' % path)
                    plt.savefig(path, usetex=False)
                    plt.close()
        
    return rflxitraminm, dcycmaxm, epocmaxm


def srch_pbox(arry, \
              
              ### maximum number of transiting objects
              maxmnumbpbox=1, \
              
              ticitarg=None, \
              
              dicttlsqinpt=None, \
              booltlsq=False, \
              
              # minimum period
              minmperi=None, \

              # maximum period
              maxmperi=None, \

              # oversampling factor (wrt to transit duration) when rebinning data to decrease the time resolution
              factduracade=2., \

              # factor by which to oversample the frequency grid
              factosam=1., \
              
              # Boolean flag to search for positive boxes
              boolsrchposi=False, \

              # number of duty cycle samples  
              numbdcyc=3, \
              
              # spread in the logarithm of duty cycle
              deltlogtdcyc=None, \
              
              # density of the star
              densstar=None, \

              # epoc steps divided by trial duration
              factdeltepocdura=0.5, \

              # detection threshold
              thrssdee=7.1, \
              
              # number of processes
              numbproc=None, \
              
              # Boolean flag to enable multiprocessing
              boolprocmult=False, \
              
              # string extension to output files
              strgextn='', \
              # path where the output data will be stored
              pathdata=None, \

              # plotting
              ## path where the output images will be stored
              pathvisu=None, \
              ## file type of the plot
              typefileplot='png', \
              ## figure size
              figrsizeydobskin=(8, 2.5), \
              ## time offset
              timeoffs=0, \
              ## data transparency
              alphraww=0.2, \
              
              # verbosity level
              typeverb=1, \
              
              # Boolean flag to turn on diagnostic mode
              booldiag=True, \

              # Boolean flag to force rerun and overwrite previous data and plots 
              boolover=True, \

             ):
    '''
    Search for periodic boxes in time-series data.
    '''
    
    boolproc = False
    listnameplot = ['sigr', 'resisigr', 'stdvresisigr', 'sdeecomp', 'rflx', 'pcur']
    if pathdata is None:
        boolproc = True
    else:
        if strgextn == '':
            pathsave = pathdata + 'pbox.csv'
        else:
            pathsave = pathdata + 'pbox_%s.csv' % strgextn
        if not os.path.exists(pathsave):
            boolproc = True
        
        dictpathplot = dict()
        for strg in listnameplot:
            dictpathplot[strg] = []
            
        if os.path.exists(pathsave):
            if typeverb > 0:
                print('Reading from %s...' % pathsave)
            
            dictpboxoutp = pd.read_csv(pathsave).to_dict(orient='list')
            for name in dictpboxoutp.keys():
                dictpboxoutp[name] = np.array(dictpboxoutp[name])
                if len(dictpboxoutp[name]) == 0:
                    dictpboxoutp[name] = np.array([])
            
            if not pathvisu is None:
                for strg in listnameplot:
                    for j in range(len(dictpboxoutp['pericomp'])):
                        dictpathplot[strg].append(pathvisu + strg + '_pbox_tce%d_%s.%s' % (j, strgextn, typefileplot))
         
                        if not os.path.exists(dictpathplot[strg][j]):
                            boolproc = True
            
    if boolproc:
        dictpboxoutp = dict()
        if pathvisu is not None:
            for name in listnameplot:
                dictpboxoutp['listpathplot%s' % name] = []
    
        print('Searching for periodic boxes in time-series data...')
        
        print('factosam')
        print(factosam)
        if booltlsq:
            import transitleastsquares
            if dicttlsqinpt is None:
                dicttlsqinpt = dict()
        
        # setup TLS
        # temp
        #ab, mass, mass_min, mass_max, radius, radius_min, radius_max = transitleastsquares.catalog_info(TIC_ID=int(ticitarg))
        
        dictpboxinte = dict()
        liststrgvarbsave = ['pericomp', 'epocmtracomp', 'depttrancomp', 'duracomp', 'sdeecomp']
        for strg in liststrgvarbsave:
            dictpboxoutp[strg] = []
        
        arrysrch = np.copy(arry)
        if boolsrchposi:
            arrysrch[:, 1] = 2. - arrysrch[:, 1]

        j = 0
        
        timeinit = timemodu.time()

        dictfact = tdpy.retr_factconv()
        
        numbtime = arrysrch[:, 0].size
        
        minmtime = np.amin(arrysrch[:, 0])
        maxmtime = np.amax(arrysrch[:, 0])
        #arrysrch[:, 0] -= minmtime

        delttime = maxmtime - minmtime
        deltfreq = 0.1 / delttime / factosam
        
        print('Initial:')
        print('minmperi')
        print(minmperi)
        print('maxmperi')
        print(maxmperi)
        #raise Exception('')

        if maxmperi is None:
            minmfreq = 2. / delttime
        else:
            minmfreq = 1. / maxmperi

        if minmperi is None:
            maxmfreq = 1. / 0.5 # 0.5 days
        else:
            maxmfreq = 1. / minmperi

        listfreq = np.arange(minmfreq, maxmfreq, deltfreq)
        listperi = 1. / listfreq
        
        if pathvisu is not None:
            numbtimeplot = 100000
            timemodlplot = np.linspace(minmtime, maxmtime, numbtimeplot)
        
        numbperi = listperi.size
        if numbperi < 3:
            print('maxmperi')
            print(maxmperi)
            print('minmperi')
            print(minmperi)
            print('numbperi')
            print(numbperi)
            raise Exception('')

        indxperi = np.arange(numbperi)
        minmperi = np.amin(listperi)
        maxmperi = np.amax(listperi)
        print('minmperi')
        print(minmperi)
        print('maxmperi')
        print(maxmperi)
        
        indxdcyc = np.arange(numbdcyc)
        listdcyc = [[] for k in indxperi]
        listperilogt = np.log10(listperi)
        
        if deltlogtdcyc is None:
            deltlogtdcyc = np.log10(2.)
        
        # assuming Solar density
        maxmdcyclogt = -2. / 3. * listperilogt - 1. + deltlogtdcyc
        if densstar is not None:
            maxmdcyclogt += -1. / 3. * np.log10(densstar)

        minmdcyclogt = maxmdcyclogt - 2. * deltlogtdcyc
        for k in indxperi:
            listdcyc[k] = np.logspace(minmdcyclogt[k], maxmdcyclogt[k], numbdcyc)
        print('Trial transit duty cycles at the smallest period')
        print(listdcyc[-1])
        print('Trial transit durations at the smallest period [hr]')
        print(listdcyc[-1] * listperi[-1] * 24)
        print('Trial transit duty cycles at the largest period')
        print(listdcyc[0])
        print('Trial transit durations at the largest period [hr]')
        print(listdcyc[0] * listperi[0] * 24)

        # cadence
        cade = np.amin(arrysrch[1:, 0] - arrysrch[:-1, 0]) * 24. # [hr]
        
        # minimum transit duration
        minmduratrantotl = listdcyc[-1][0] * listperi[-1] * 24
        
        # maximum transit duration
        maxmduratrantotl = listdcyc[0][-1] * listperi[0] * 24
        
        if minmduratrantotl < factduracade * cade:
            print('Either the minimum transit duration is too small or the cadence is too large.')
            print('minmduratrantotl')
            print(minmduratrantotl)
            print('factduracade')
            print(factduracade)
            print('cade [hr]')
            print(cade)
            raise Exception('')
        
        # number of rebinned data sets
        numblevlrebn = 10
        indxlevlrebn = np.arange(numblevlrebn)
        
        # list of transit durations when rebinned data sets will be used
        listduratrantotllevl = np.linspace(minmduratrantotl, maxmduratrantotl, numblevlrebn)
        
        print('listduratrantotllevl')
        print(listduratrantotllevl)
        
        # rebinned data sets
        print('Number of data points: %d...' % numbtime)
        listarrysrch = []
        for b in indxlevlrebn:
            delt = listduratrantotllevl[b] / 24. / factduracade
            arryrebn = rebn_tser(arrysrch, delt=delt)
            indx = np.where(np.isfinite(arryrebn[:, 1]))[0]
            print('Number of data points in binned data set for Delta time %g [min]: %d' % (delt * 24. * 60., arryrebn.shape[0]))
            arryrebn = arryrebn[indx, :]
            listarrysrch.append(arryrebn)
            print('Number of data points in binned data set for Delta time %g [min]: %d' % (delt * 24. * 60., arryrebn.shape[0]))
            print('')
        listepoc = [[[] for l in range(numbdcyc)] for k in indxperi]
        numbtria = np.zeros(numbperi, dtype=int)
        for k in indxperi:
            for l in indxdcyc:
                diffepoc = max(cade / 24., factdeltepocdura * listperi[k] * listdcyc[k][l])
                listepoc[k][l] = np.arange(minmtime, minmtime + listperi[k], diffepoc)
                numbtria[k] += len(listepoc[k][l])
                
        dflx = arrysrch[:, 1] - 1.
        stdvdflx = arrysrch[:, 2]
        varidflx = stdvdflx**2
        
        print('Number of trial periods: %d...' % numbperi)
        print('Number of trial computations for the smallest period: %d...' % numbtria[-1])
        print('Number of trial computations for the largest period: %d...' % numbtria[0])
        print('Total number of trial computations: %d...' % np.sum(numbtria))

        while True:
            
            if maxmnumbpbox is not None and j >= maxmnumbpbox:
                break
            
            # mask out the detected transit
            if j > 0:
                ## remove previously detected periodic box from the rebinned data
                pericomp = [dictpboxoutp['pericomp'][j]]
                epocmtracomp = [dictpboxoutp['epocmtracomp'][j]]
                radicomp = [dictfact['rsre'] * np.sqrt(dictpboxoutp['depttrancomp'][j] * 1e-3)]
                cosicomp = [0]
                rsmacomp = [retr_rsmacomp(dictpboxoutp['pericomp'][j], dictpboxoutp['duracomp'][j], cosicomp[0])]
                    
                for b in indxlevlrebn:
                    ## evaluate model at all resolutions
                    dictoutp = eval_modl(listarrysrch[b][:, 0], 'psys', pericomp=pericomp, epocmtracomp=epocmtracomp, \
                                                                                        rsmacomp=rsmacomp, cosicomp=cosicomp, rratcomp=rratcomp)
                    ## subtract it from data
                    listarrysrch[b][:, 1] -= (dictoutp['rflx'][b] - 1.)
                
                    if (dictpboxinte['rflx'][b] == 1.).all():
                        raise Exception('')

            if booltlsq:
                objtmodltlsq = transitleastsquares.transitleastsquares(arrysrch[:, 0], lcurpboxmeta)
                objtresu = objtmodltlsq.power(\
                                              # temp
                                              #u=ab, \
                                              **dicttlsqinpt, \
                                              #use_threads=1, \
                                             )

                dictpbox = dict()
                dictpboxinte['listperi'] = objtresu.periods
                dictpboxinte['listsigr'] = objtresu.power
                
                dictpboxoutp['pericomp'].append(objtresu.period)
                dictpboxoutp['epocmtracomp'].append(objtresu.T0)
                dictpboxoutp['duracomp'].append(objtresu.duration)
                dictpboxoutp['depttrancomp'].append(objtresu.depth * 1e3)
                dictpboxoutp['sdeecomp'].append(objtresu.SDE)
                dictpboxoutp['prfp'].append(objtresu.FAP)
                
                if objtresu.SDE < thrssdee:
                    break
                
                dictpboxinte['rflxtsermodl'] = objtresu.model_lightcurve_model
                
                if pathvisu is not None:
                    dictpboxinte['listtimetran'] = objtresu.transit_times
                    dictpboxinte['timemodl'] = objtresu.model_lightcurve_time
                    dictpboxinte['phasmodl'] = objtresu.model_folded_phase
                    dictpboxinte['rflxpsermodl'] = objtresu.model_folded_model
                    dictpboxinte['phasdata'] = objtresu.folded_phase
                    dictpboxinte['rflxpserdata'] = objtresu.folded_y

            else:
                
                if boolprocmult:
                    
                    if numbproc is None:
                        #numbproc = multiprocessing.cpu_count() - 1
                        numbproc = int(0.8 * multiprocessing.cpu_count())
                    
                    print('Generating %d processes...' % numbproc)
                    
                    objtpool = multiprocessing.Pool(numbproc)
                    numbproc = objtpool._processes
                    indxproc = np.arange(numbproc)

                    listperiproc = [[] for i in indxproc]
                    
                    binsperiproc = tdpy.icdf_powr(np.linspace(0., 1., numbproc + 1)[1:-1], np.amin(listperi), np.amax(listperi), 1.97)
                    binsperiproc = np.concatenate((np.array([-np.inf]), binsperiproc, np.array([np.inf])))
                    indxprocperi = np.digitize(listperi, binsperiproc, right=False) - 1
                    for i in indxproc:
                        indx = np.where(indxprocperi == i)[0]
                        listperiproc[i] = listperi[indx]
                    data = objtpool.map(partial(srch_pbox_work, listperiproc, listarrysrch, listdcyc, listepoc, listduratrantotllevl), indxproc)
                    listrflxitra = np.concatenate([data[k][0] for k in indxproc])
                    listdeptmaxm = np.concatenate([data[k][1] for k in indxproc])
                    listdcycmaxm = np.concatenate([data[k][2] for k in indxproc])
                    listepocmaxm = np.concatenate([data[k][3] for k in indxproc])
                else:
                    listrflxitra, listdcycmaxm, listepocmaxm = srch_pbox_work([listperi], listarrysrch, listdcyc, listepoc, listduratrantotllevl, 0)
                
                listdept = (np.median(listarrysrch[b][:, 1]) - listrflxitra) * 1e3 # [ppt])
                listsigr = listdept
                if (~np.isfinite(listsigr)).any():
                    raise Exception('')

                sizekern = 51
                listresisigr = listsigr - scipy.ndimage.median_filter(listsigr, size=sizekern)
                #listresisigr = listresisigr**2
                liststdvresisigr = retr_stdvwind(listresisigr, sizekern, boolcuttpeak=True)
                listsdee = listresisigr / liststdvresisigr
                #listsdee -= np.amin(listsdee)
                
                indxperimpow = np.argmax(listsdee)
                sdee = listsdee[indxperimpow]
                
                if not np.isfinite(sdee):
                    print('Warning! SDE is infinite! Making it zero.')
                    sdee = 0.
                    print('arry')
                    summgene(arry)
                    for b in indxlevlrebn:
                        print('listarrysrch[b]')
                        summgene(listarrysrch[b])
                    print('listsigr')
                    summgene(listsigr)
                    indxperizerostdv = np.where(liststdvresisigr == 0)[0]
                    print('indxperizerostdv')
                    summgene(indxperizerostdv)
                    print('liststdvresisigr')
                    summgene(liststdvresisigr)
                    #raise Exception('')

                dictpboxoutp['sdeecomp'].append(sdee)
                dictpboxoutp['pericomp'].append(listperi[indxperimpow])
                dictpboxoutp['duracomp'].append(24. * listdcycmaxm[indxperimpow] * listperi[indxperimpow]) # [hours]
                dictpboxoutp['epocmtracomp'].append(listepocmaxm[indxperimpow])
                dictpboxoutp['depttrancomp'].append(listdept[indxperimpow])
                
                print('sdeecomp')
                print(sdee)

                # best-fit orbit
                dictpboxinte['listperi'] = listperi
                
                print('temp: assuming power is SNR')
                dictpboxinte['listsigr'] = listsigr
                dictpboxinte['listresisigr'] = listresisigr
                dictpboxinte['liststdvresisigr'] = liststdvresisigr
                dictpboxinte['listsdeecomp'] = listsdee
                
                # to be deleted because these are rebinned and model may be all 1s
                #if booldiag and (dictpboxinte['rflxtsermodl'][b] == 1).all():
                #    print('listarrysrch[b][:, 0]')
                #    summgene(listarrysrch[b][:, 0])
                #    print('radistar')
                #    print(radistar)
                #    print('pericomp')
                #    print(pericomp)
                #    print('epocmtracomp')
                #    print(epocmtracomp)
                #    print('rsmacomp')
                #    print(rsmacomp)
                #    print('cosicomp')
                #    print(cosicomp)
                #    print('radicomp')
                #    print(radicomp)
                #    print('dictpboxinte[rflxtsermodl[b]]')
                #    summgene(dictpboxinte['rflxtsermodl'][b])
                #    raise Exception('')

                if pathvisu is not None:
                    for strg in listnameplot:
                        for j in range(len(dictpboxoutp['pericomp'])):
                            pathplot = pathvisu + strg + '_pbox_tce%d_%s.%s' % (j, strgextn, typefileplot)
                            dictpathplot[strg].append(pathplot)
            
                    pericomp = [dictpboxoutp['pericomp'][j]]
                    epocmtracomp = [dictpboxoutp['epocmtracomp'][j]]
                    cosicomp = [0]
                    rsmacomp = [retr_rsmacomp(dictpboxoutp['pericomp'][j], dictpboxoutp['duracomp'][j], cosicomp[0])]
                    rratcomp = [np.sqrt(dictpboxoutp['depttrancomp'][j] * 1e-3)]
                    dictoutp = eval_modl(timemodlplot, 'psys', pericomp=pericomp, epocmtracomp=epocmtracomp, \
                                                                                            rsmacomp=rsmacomp, cosicomp=cosicomp, rratcomp=rratcomp, typesyst='psys')
                    dictpboxinte['rflxtsermodl'] = dictoutp['rflx']
                    
                    arrymetamodl = np.zeros((numbtimeplot, 3))
                    arrymetamodl[:, 0] = timemodlplot
                    arrymetamodl[:, 1] = dictpboxinte['rflxtsermodl']
                    arrypsermodl = fold_tser(arrymetamodl, dictpboxoutp['epocmtracomp'][j], dictpboxoutp['pericomp'][j], phasshft=0.5)
                    arrypserdata = fold_tser(listarrysrch[0], dictpboxoutp['epocmtracomp'][j], dictpboxoutp['pericomp'][j], phasshft=0.5)
                        
                    dictpboxinte['timedata'] = listarrysrch[0][:, 0]
                    dictpboxinte['rflxtserdata'] = listarrysrch[0][:, 1]
                    dictpboxinte['phasdata'] = arrypserdata[:, 0]
                    dictpboxinte['rflxpserdata'] = arrypserdata[:, 1]

                    dictpboxinte['timemodl'] = arrymetamodl[:, 0]
                    dictpboxinte['phasmodl'] = arrypsermodl[:, 0]
                    dictpboxinte['rflxpsermodl'] = arrypsermodl[:, 1]
                
                    print('boolsrchposi')
                    print(boolsrchposi)
                    if boolsrchposi:
                        dictpboxinte['rflxpsermodl'] = 2. - dictpboxinte['rflxpsermodl']
                        dictpboxinte['rflxtsermodl'] = 2. - dictpboxinte['rflxtsermodl']
                        dictpboxinte['rflxpserdata'] = 2. - dictpboxinte['rflxpserdata']
           
            if pathvisu is not None:
                strgtitl = 'P=%.3f d, $T_0$=%.3f, Dep=%.2g ppt, Dur=%.2g hr, SDE=%.3g' % \
                            (dictpboxoutp['pericomp'][j], dictpboxoutp['epocmtracomp'][j], dictpboxoutp['depttrancomp'][j], \
                            dictpboxoutp['duracomp'][j], dictpboxoutp['sdeecomp'][j])
                
                # plot power spectra
                for a in range(4):
                    if a == 0:
                        strg = 'sigr'
                    if a == 1:
                        strg = 'resisigr'
                    if a == 2:
                        strg = 'stdvresisigr'
                    if a == 3:
                        strg = 'sdeecomp'

                    figr, axis = plt.subplots(figsize=figrsizeydobskin)
                    
                    axis.axvline(dictpboxoutp['pericomp'][j], alpha=0.4, lw=3)
                    minmxaxi = np.amin(dictpboxinte['listperi'])
                    maxmxaxi = np.amax(dictpboxinte['listperi'])
                    for n in range(2, 10):
                        xpos = n * dictpboxoutp['pericomp'][j]
                        if xpos > maxmxaxi:
                            break
                        axis.axvline(xpos, alpha=0.4, lw=1, linestyle='dashed')
                    for n in range(2, 10):
                        xpos = dictpboxoutp['pericomp'][j] / n
                        if xpos < minmxaxi:
                            break
                        axis.axvline(xpos, alpha=0.4, lw=1, linestyle='dashed')
                    
                    axis.set_ylabel('Power')
                    axis.set_xlabel('Period [days]')
                    axis.set_xscale('log')
                    axis.plot(dictpboxinte['listperi'], dictpboxinte['list' + strg], color='black', lw=0.5)
                    axis.set_title(strgtitl)
                    plt.subplots_adjust(bottom=0.2)
                    path = dictpathplot[strg][j]
                    dictpboxoutp['listpathplot%s' % strg].append(path)
                    print('Writing to %s...' % path)
                    plt.savefig(path)
                    plt.close()
                
                # plot data and model time-series
                figr, axis = plt.subplots(figsize=figrsizeydobskin)
                lcurpboxmeta = listarrysrch[0][:, 1]
                if boolsrchposi:
                    lcurpboxmetatemp = 2. - lcurpboxmeta
                else:
                    lcurpboxmetatemp = lcurpboxmeta
                axis.plot(listarrysrch[0][:, 0] - timeoffs, lcurpboxmetatemp, alpha=alphraww, marker='o', ms=1, ls='', color='gray')
                axis.plot(dictpboxinte['timemodl'] - timeoffs, dictpboxinte['rflxtsermodl'], color='b')
                if timeoffs == 0:
                    axis.set_xlabel('Time [days]')
                else:
                    axis.set_xlabel('Time [BJD-%d]' % timeoffs)
                axis.set_ylabel('Relative flux');
                if j == 0:
                    ylimtserinit = axis.get_ylim()
                else:
                    axis.set_ylim(ylimtserinit)
                axis.set_title(strgtitl)
                plt.subplots_adjust(bottom=0.2)
                path = dictpathplot['rflx'][j]
                dictpboxoutp['listpathplotrflx'].append(path)
                print('Writing to %s...' % path)
                plt.savefig(path, dpi=200)
                plt.close()

                # plot data and model phase-series
                figr, axis = plt.subplots(figsize=figrsizeydobskin)
                axis.plot(dictpboxinte['phasdata'], dictpboxinte['rflxpserdata'], marker='o', ms=1, ls='', alpha=alphraww, color='gray')
                axis.plot(dictpboxinte['phasmodl'], dictpboxinte['rflxpsermodl'], color='b')
                axis.set_xlabel('Phase')
                axis.set_ylabel('Relative flux');
                if j == 0:
                    ylimpserinit = axis.get_ylim()
                else:
                    axis.set_ylim(ylimpserinit)
                axis.set_title(strgtitl)
                plt.subplots_adjust(bottom=0.2)
                path = dictpathplot['pcur'][j]
                dictpboxoutp['listpathplotpcur'].append(path)
                print('Writing to %s...' % path)
                plt.savefig(path, dpi=200)
                plt.close()
            
            print('dictpboxoutp[sdee]')
            print(dictpboxoutp['sdeecomp'])
            print('thrssdee')
            print(thrssdee)
            j += 1
        
            if sdee < thrssdee or indxperimpow == listsdee.size - 1:
                break
        
        # make the BLS features arrays
        for name in dictpboxoutp.keys():
            dictpboxoutp[name] = np.array(dictpboxoutp[name])
        
        print('dictpboxoutp')
        print(dictpboxoutp)
        pd.DataFrame.from_dict(dictpboxoutp).to_csv(pathsave, index=False)
                
        timefinl = timemodu.time()
        timetotl = timefinl - timeinit
        timeredu = timetotl / numbtime / np.sum(numbtria)
        
        print('srch_pbox() took %.3g seconds in total and %g ns per observation and trial.' % (timetotl, timeredu * 1e9))

    return dictpboxoutp


def init( \
         
         # a label distinguishing the run to be used in the plots
         lablcnfg=None, \
         
         # a string distinguishing the run to be used in the file names
         strgcnfg=None, \
         
         # target identifiers
         ## string to search on MAST
         strgmast=None, \
         
         ## TIC ID
         ticitarg=None, \
         
         ## TOI ID
         toiitarg=None, \
         
         ## RA
         rasctarg=None, \
         
         ## Dec
         decltarg=None, \

         ## a string for the label of the target
         labltarg=None, \
         
         ## a string for the folder name and file name extensions
         strgtarg=None, \
         
         # string indicating the cluster of targets
         strgclus=None, \
        
         ## Boolean flag indicating whether the input photometric data will be median-normalized
         boolnormphot=True, \
         
         # options changing the overall execution
         ## Boolean flag to enforce offline operation
         boolforcoffl=False, \

         ## Boolean flag to search for and analyze time-domain data on the target
         booltserdata=True, \
        
         
         # target visibility from a given observatory over a given night and year
         ## Boolean flag to calculate visibility of the target
         boolcalcvisi=False, \
         
         ## Boolean flag to plot visibility of the target
         boolplotvisi=None, \
         
         ## latitude of the observatory for the visibility calculation
         latiobvt=None, \
         
         ## longitude of the observatory for the visibility calculation
         longobvt=None, \
         
         ## height of the observatory for the visibility calculation
         heigobvt=None, \
         
         ## string of time for the night
         strgtimeobvtnigh=None, \
         
         ## string of time for the beginning of the year
         strgtimeobvtyear=None, \
         
         ## list of time difference samples for the year
         listdelttimeobvtyear=None, \
         
         ## local time offset for the visibility calculation
         offstimeobvt=0., \
            
         # dictionary for parameters of the true generative model
         dicttrue=None, \

         # dictionary for parameters of the fitting generative model
         dictfitt=None, \

         ## general plotting
         ## Boolean flag to make plots
         boolplot=True, \
         
         ## Boolean flag to plot target features along with the features of the parent population
         boolplotpopl=False, \
         
         ## Boolean flag to plot DV reports
         boolplotdvrp=None, \
         
         ## Boolean flag to plot the time-series
         boolplottser=None, \
         
         ## Boolean flag to animate the orbit
         boolanimorbt=False, \
         
         ## time offset to subtract from the time axes, which is otherwise automatically estimated
         timeoffs=None, \
         
         ## file type of the plot
         typefileplot='png', \

         ## Boolean flag to write planet name on plots
         boolwritplan=True, \
         
         ## Boolean flag to rasterize the raw time-series on plots
         boolrastraww=True, \
         
         ## list of transit depths to indicate on the light curve and phase curve plots
         listdeptdraw=None, \
         
         # list of experiments whose data are to be downloaded
         liststrgexpr=None, \

         # paths
         ## the path of the folder in which the target folder will be placed
         pathbase=None, \
         
         ## the path of the target folder
         pathtarg=None, \
         
         ## the path of the target data folder
         pathdatatarg=None, \
         
         ## the path of the target image folder
         pathvisutarg=None, \
         
         # data
         ## string indicating the type of data
        
         ## data retrieval
         ### subset of TESS sectors to retrieve
         listtsecsele=None, \
         
         ### Boolean flag to apply quality mask
         boolmaskqual=True, \
         
         ### Boolean flag to only utilize SPOC light curves on a local disk
         boolutiltesslocl=False, \

         ### Boolean flag to only consider FFI data
         boolffimonly=False, \

         ### Boolean flag to only consider TPF data (2-min or 20-sec)
         #### deprecated? to be deleted?
         booltpxfonly=False, \

         ### name of the data product of lygos indicating which analysis has been used for photometry
         nameanlslygo='psfn', \

         ### Boolean flag to use 20-sec TPF when available
         boolfasttpxf=True, \
             

         # input data
         ## path of the CSV file containing the input data
         listpathdatainpt=None, \
         
         ## input data as a dictionary of lists of numpy arrays
         listarrytser=None, \
         
         ## list of TESS sectors for the input data
         listtsecinpt=None, \
         
         
         ## list of values for the energy axis
         listener=None, \
         
         ## label for the energy axis
         lablener=None, \
         
         # TPF light curve extraction pipeline (FFIs are always extracted by lygos)
         ## 'lygos': lygos
         ## 'SPOC': SPOC
         typelcurtpxftess='SPOC', \
         
         ## type of SPOC light curve: 'PDC', 'SAP'
         typedataspoc='PDC', \
                  
         # type of data for each data kind, instrument, and chunk
         ## 'simutargsynt': simulated data on a synthetic target
         ## 'simutargpart': simulated data on a particular target with a particular observational baseline 
         liststrgtypedata=None, \

         ## list of labels indicating instruments
         listlablinst=None, \
         
         ## list of strings indicating instruments
         liststrginst=None, \
         
         ## list of strings indicating chunks in the filenames
         liststrgchun=None, \
         
         ## list of strings indicating chunks in the plots
         listlablchun=None, \
         
         ## list of chunk indices for each instrument
         listindxchuninst=None, \
         
         ## input dictionary for lygos                                
         dictlygoinpt=None, \
         
         ## time limits to mask
         listlimttimemask=None, \
        
         # analyses
         ## list of types of analyses for time series data
         listtypeanls=None, \
         
         ## transit search
         ### input dictionary to the search pipeline for periodic boxes
         dictpboxinpt=None, \
        
         ### input dictionary to the search pipeline for single transits
         dictsrchtransinginpt=None, \
         
         ## flare search
         ### threshold percentile for detecting stellar flares
         thrssigmflar=7., \

         ### input dictionary to the search pipeline for flares
         dictsrchflarinpt=dict(), \
   
         # Boolean flag to search for flares
         boolsrchflar=None, \
        
         # fitting
         # Boolean flag to reject the lowest log-likelihood during log-likelihood calculation
         boolrejeoutlllik=False, \

         # model
         # type of inference
         ## 'samp': sample from the posterior
         ## 'opti': optimize the likelihood
         typeinfe='samp', \

         # list of types of models for time series data
         ## typemodl
         ### 'psys': gravitationally bound system of a star and potentially transiting planets
         ### 'psysphas': gravitationally bound system of a star and potentially transiting planets with phase modulations
         ### 'ssys': gravitationally bound system of potentially transiting two stars
         ### 'cosc': gravitationally bound system of a star and potentially transiting compact companion
         ### 'flar': stellar flare
         ### 'agns': AGN
         ### 'spot': stellar spot
         ### 'supn': supernova
         ### 'stargpro': star with variability described by a Gaussian Process

         # stellar limb darkening
         ## a string indicating how limb darkening coefficients change across energies
         ### 'cons': constant at all energies
         ### 'line': linear change across energies
         ### 'ener': free at all energies
         #typemodllmdkener='cons', \
         ## a string indicating how limb darkening coefficients change across energies
         ### 'cons': constant at all angles
         ### 'line': linear in the cosine of the angle between the observer and the surface normal (i.e., gamma)
         ### 'quad': quadratic in the cosine of the angle between the observer and the surface normal (i.e., gamma)
         #typemodllmdkterm='quad', \
         
         # limits of time between which the fit is performed
         limttimefitt=None, \

         ## flare model
         ### type of model for finding flares
         typemodlflar='outl', \

         ## transit model
         ## dilution: None (no correction), 'lygos' for estimation via lygos, or float value
         dilu=None, \
         
         ## priors
         ### Boolean flag to detrend the photometric time-series before estimating the priors
         boolbdtr=None, \
         ### baseline detrending
         #### minimum time interval for breaking the time-series into regions, which will be detrended separately
         timebrekregi=0.1, \
         #### Boolean flag to break the time-series into regions
         boolbrekregi=False, \

         #### type of the baseline model
         typebdtr='gpro', \
         #### order of the spline
         ordrspln=3, \
         #### time scale for median-filtering detrending
         timescalbdtrmedi=2., \
         #### time scale for spline baseline detrending
         listtimescalbdtrspln=[2.], \

         ### maximum frequency (per day) for LS periodogram
         maxmfreqlspe=None, \
         
         # threshold BLS SDE for disposing the target as positive
         thrssdeecosc=10., \
                
         # threshold LS periodogram power for disposing the target as positive
         thrslspecosc=0.2, \
                
         # type of model for lensing
         ## 'phdy': photodynamically calculated
         ## 'gaus': Gaussian
         typemodllens='phdy', \

         ### type of priors for stars: 'tici', 'exar', 'inpt'
         typepriostar=None, \

         # type of priors for planets
         typepriocomp=None, \
         
         # Boolean flag to turn on transit for each companion
         booltrancomp=None, \

         ### photometric and RV model
         #### means
         rratcompprio=None, \
         rsmacompprio=None, \
         epocmtracompprio=None, \
         pericompprio=None, \
         cosicompprio=None, \
         ecoscompprio=None, \
         esincompprio=None, \
         rvelsemaprio=None, \
         #### uncertainties
         stdvrratcompprio=None, \
         stdvrsmacompprio=None, \
         stdvepocmtracompprio=None, \
         stdvpericompprio=None, \
         stdvcosicompprio=None, \
         stdvecoscompprio=None, \
         stdvesincompprio=None, \
         stdvrvelsemaprio=None, \
        
         ### others 
         #### mean
         projoblqprio=None, \
         #### uncertainties
         stdvprojoblqprio=None, \

         radistar=None, \
         massstar=None, \
         tmptstar=None, \
         rascstar=None, \
         declstar=None, \
         vsiistar=None, \
         
         vmagsyst=None, \
         jmagsyst=None, \
         hmagsyst=None, \
         kmagsyst=None, \

         stdvradistar=None, \
         stdvmassstar=None, \
         stdvtmptstar=None, \
         stdvrascstar=None, \
         stdvdeclstar=None, \
         stdvvsiistar=None, \

         ## Boolean flag to perform inference on the phase-folded (onto the period of the first planet) and binned data
         boolinfefoldbind=False, \
         ## Boolean flag to model the out-of-transit data to learn a background model
         boolallebkgdgaus=False, \
         # output
         ### list of offsets for the planet annotations in the TSM/ESM plot
         offstextatmoraditmpt=None, \
         offstextatmoradimetr=None, \
         
         # exoplanet specifics
         # planet names
         # string to pull the priors from the NASA Exoplanet Archive
         strgexar=None, \

         ## list of letters to be assigned to planets
         liststrgcomp=None, \
         
         # energy scale over which to detrend the inferred spectrum
         enerscalbdtr=None, \

         # factor to scale the size of text in the figures
         factsizetextfigr=1., \

         ## list of colors to be assigned to planets
         listcolrcomp=None, \
         
         ## Boolean flag to assign them letters *after* ordering them in orbital period, unless liststrgcomp is specified by the user
         boolordrplanname=True, \
        
         # population contexualization
         ## Boolean flag to include the ExoFOP catalog in the comparisons to exoplanet population
         boolexofpopl=True, \
        
         # Boolean flag to ignore any existing file and overwrite
         boolwritover=False, \
         
         # Boolean flag to diagnose the code using potentially computationally-expensive sanity checks, which may slow down the execution
         booldiag=True, \
         
         # type of verbosity
         typeverb=1, \

        ):
    '''
    Main function of the miletos pipeline.
    '''
    
    # construct global object
    gdat = tdpy.gdatstrt()
    
    # copy locals (inputs) to the global object
    dictinpt = dict(locals())
    for attr, valu in dictinpt.items():
        if '__' not in attr and attr != 'gdat':
            setattr(gdat, attr, valu)

    # paths
    gdat.pathbasemile = os.environ['MILETOS_DATA_PATH'] + '/'
    if gdat.pathbase is None:
        gdat.pathbase = gdat.pathbasemile
    
    # measure initial time
    gdat.timeinit = modutime.time()

    # string for date and time
    gdat.strgtimestmp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if gdat.typeverb > 0:
        print('miletos initialized at %s...' % gdat.strgtimestmp)
    
    # check input arguments
    if not gdat.boolplot and gdat.boolplottser:
        raise Exception('')
    
    if gdat.boolplotvisi and not gdat.boolcalcvisi:
        raise Exception('')
    
    if gdat.boolplotvisi is None:
        gdat.boolplotvisi = gdat.boolcalcvisi
    
    # if either of dictfitt or dicttrue is defined, mirror it to the other
    if gdat.dicttrue is None and gdat.dictfitt is None:
        gdat.dicttrue = dict()
        gdat.dictfitt = dict()
    elif gdat.dicttrue is None and gdat.dictfitt is not None:
        gdat.dicttrue = gdat.dictfitt
    elif gdat.dicttrue is not None and gdat.dictfitt is None:
        gdat.dictfitt = gdat.dicttrue
    
    if gdat.typeverb > 1:
        print('gdat.dicttrue')
        print(gdat.dicttrue)
        print('gdat.dictfitt')
        print(gdat.dictfitt)

    # paths
    gdat.pathbaselygo = os.environ['LYGOS_DATA_PATH'] + '/'
    
    # check input arguments
    if not (gdat.pathtarg is not None and gdat.pathbase is None and gdat.pathdatatarg is None and gdat.pathvisutarg is None or \
            gdat.pathtarg is None and gdat.pathbase is not None and gdat.pathdatatarg is None and gdat.pathvisutarg is None or \
            gdat.pathtarg is None and gdat.pathbase is None and gdat.pathdatatarg is not None and gdat.pathvisutarg is not None):
        print('gdat.pathtarg')
        print(gdat.pathtarg)
        print('gdat.pathbase')
        print(gdat.pathbase)
        print('gdat.pathdatatarg')
        print(gdat.pathdatatarg)
        print('gdat.pathvisutarg')
        print(gdat.pathvisutarg)
        raise Exception('')
    
    ## ensure that target and star coordinates are not provided separately
    if gdat.rasctarg is not None and gdat.rascstar is not None:
        raise Exception('')
    if gdat.decltarg is not None and gdat.declstar is not None:
        raise Exception('')

    gdat.arrytser = dict()
    ## ensure target identifiers are not conflicting
    if gdat.listarrytser is None:
        gdat.listarrytser = dict()
        if gdat.ticitarg is None and gdat.strgmast is None and gdat.toiitarg is None and (gdat.rasctarg is None or gdat.decltarg is None):
            print('Warning: No TIC ID (ticitarg), RA&DEC (rasctarg and decltarg), MAST key (strgmast) or a TOI ID (toiitarg) wad provided.')
        
        if gdat.ticitarg is not None and (gdat.strgmast is not None or gdat.toiitarg is not None or gdat.rasctarg is not None or gdat.decltarg is not None):
            raise Exception('Either a TIC ID (ticitarg), RA&DEC (rasctarg and decltarg), MAST key (strgmast) or a TOI ID (toiitarg) should be provided.')
        if gdat.strgmast is not None and (gdat.ticitarg is not None or gdat.toiitarg is not None or gdat.rasctarg is not None or gdat.decltarg is not None):
            raise Exception('Either a TIC ID (ticitarg), RA&DEC (rasctarg and decltarg), MAST key (strgmast) or a TOI ID (toiitarg) should be provided.')
        if gdat.toiitarg is not None and (gdat.strgmast is not None or gdat.ticitarg is not None or gdat.rasctarg is not None or gdat.decltarg is not None):
            raise Exception('Either a TIC ID (ticitarg), RA&DEC (rasctarg and decltarg), MAST key (strgmast) or a TOI ID (toiitarg) should be provided.')
        if gdat.strgmast is not None and (gdat.ticitarg is not None or gdat.toiitarg is not None or gdat.rasctarg is not None or gdat.decltarg is not None):
            raise Exception('Either a TIC ID (ticitarg), RA&DEC (rasctarg and decltarg), MAST key (strgmast) or a TOI ID (toiitarg) should be provided.')
    
    # dictionary to be returned
    gdat.dictmileoutp = dict()
    
    gdat.boolsrchpbox = False
    gdat.boolcalclspe = False
    
    if gdat.booltserdata:
        
        gdat.boolusedrvel = False
        gdat.boolusedrflx = True

        # types of data
        gdat.liststrgdatatser = ['lcur', 'rvel']
        gdat.numbdatatser = len(gdat.liststrgdatatser)
        gdat.indxdatatser = np.arange(gdat.numbdatatser)
        
        # labels of the instruments
        if gdat.listlablinst is None:
            gdat.listlablinst = [['TESS'], []]
        
        if gdat.typeverb > 1:
            print('gdat.listlablinst')
            print(gdat.listlablinst)
        
        # instruments
        gdat.numbinst = np.empty(gdat.numbdatatser, dtype=int)
        gdat.indxinst = [[] for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            gdat.numbinst[b] = len(gdat.listlablinst[b])
            gdat.indxinst[b] = np.arange(gdat.numbinst[b])
        
        if gdat.booldiag:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if len(gdat.listlablinst[b][p]) == 0:
                        print('')
                        print('')
                        print('')
                        raise Exception('gdat.listlablinst[b][p] is empty.')
            
            if len(gdat.listlablinst) != 2:
                print('')
                print('')
                print('')
                raise Exception('gdat.listlablinst should be a list with two elements.')

        # number of energy bins for each photometric data set
        gdat.numbener = [[] for p in gdat.indxinst[0]]
        
        # list of data types ('obsd', 'simutargsynt', or 'simutargpart') for each instrument for both light curve and RV data
        if gdat.liststrgtypedata is None:
            gdat.liststrgtypedata = [[] for b in gdat.indxdatatser]
            for b in gdat.indxdatatser:
                gdat.liststrgtypedata[b] = ['obsd' for p in gdat.indxinst[b]]
        
        # Boolean flag indicating if the simulated target is a synthetic one
        gdat.booltargsynt = False
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if gdat.liststrgtypedata[b][p] == 'simutargsynt':
                    gdat.booltargsynt = True
        
        if gdat.typeverb > 0:
            print('gdat.liststrgtypedata')
            print(gdat.liststrgtypedata)

        if gdat.liststrginst is None:
            gdat.liststrginst = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    gdat.liststrginst[b][p] = ''.join(gdat.listlablinst[b][p].split(' '))
        if gdat.booldiag:
            if not isinstance(gdat.liststrginst[0], list):
                raise Exception('')
            if not isinstance(gdat.liststrginst[1], list):
                raise Exception('')
            if not isinstance(gdat.listlablinst[0], list):
                raise Exception('')
            if not isinstance(gdat.listlablinst[1], list):
                raise Exception('')
            
            for b in gdat.indxdatatser:
                if len(gdat.liststrginst[b]) != len(gdat.listlablinst[b]):
                    print('')
                    print('')
                    print('')
                    print('gdat.liststrginst')
                    print(gdat.liststrginst)
                    print('gdat.listlablinst')
                    print(gdat.listlablinst)
                    raise Exception('len(gdat.liststrginst[b]) != len(gdat.listlablinst[b])')
        
        ## Boolean flag indicating whether any data is simulated
        gdat.boolsimurflx = False
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if gdat.liststrgtypedata[b][p].startswith('simu'):
                    gdat.boolsimurflx = True
        
        ## Boolean flag to query MAST
        gdat.boolretrlcurmast = False
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if (gdat.liststrginst[b][p] == 'TESS' or gdat.liststrginst[b][p] == 'K2' or \
                           gdat.liststrginst[b][p] == 'Kepler' or gdat.liststrginst[b][p] == 'HST' or gdat.liststrginst[b][p].startswith('JWST')) \
                                                                                and not gdat.liststrgtypedata[b][p].startswith('simugene') \
                                                                                and not gdat.liststrgtypedata[b][p].startswith('inpt'):
                    gdat.boolretrlcurmast = True
        
        # list of models to be fitted to the data
        gdat.liststrgmodl = ['fitt']
        if gdat.boolsimurflx:
            gdat.liststrgmodl += ['true']
        
            gdat.true = tdpy.gdatstrt()
            if gdat.dicttrue is not None:
                for name, valu in gdat.dicttrue.items():
                    setattr(gdat.true, name, valu)
            
    gdat.fitt = tdpy.gdatstrt()
    if gdat.dictfitt is not None:
        print('Transferring the contents of dictfitt to gdat...')
        for name, valu in gdat.dictfitt.items():
            print('name')
            print(name)
            print('valu')
            print(valu)
            setattr(gdat.fitt, name, valu)
    
    gdat.maxmradisrchmast = 10. # arcsec
    gdat.strgradi = '%gs' % gdat.maxmradisrchmast
    
    if gdat.booltserdata:
        
        # Boolean flag to perform inference
        gdat.boolinfe = hasattr(gdat.fitt, 'typemodl')
        
        if gdat.typeverb > 0:
            if gdat.boolinfe:
                print('Type of fitting model: %s' % gdat.fitt.typemodl)
            else:
                print('No fitting will be performed.')

        if gdat.boolinfe:
            setp_modlinit(gdat, 'fitt')
        
        if gdat.boolplottser is None:
            gdat.boolplottser = gdat.boolplot
        
        if gdat.boolplotdvrp is None:
            gdat.boolplotdvrp = gdat.boolplot
        
        if gdat.dictlygoinpt is None:
            gdat.dictlygoinpt = dict()
        
        # data validation (DV) report
        ## list of dictionaries holding the paths and DV report positions of plots
        if gdat.boolplot:
            gdat.listdictdvrp = [[]]
        
    if (gdat.boolcalcvisi or gdat.boolplotpopl or gdat.booltserdata) and (gdat.toiitarg is not None or gdat.ticitarg is not None) \
                                                                                                         and gdat.fitt.typemodl != 'supn':
        gdat.dictexof = ephesos.retr_dicttoii()

    # conversion factors
    gdat.dictfact = tdpy.retr_factconv()

    # settings
    ## plotting
    gdat.numbcyclcolrplot = 300
    gdat.alphraww = 0.2
    
    if gdat.lablener is None:
        gdat.lablener = 'Wavelength'
    
    if gdat.enerscalbdtr is None:
        gdat.enerscalbdtr = 0.1 # [um]

    gdat.figrsize = [6, 4]
    gdat.figrsizeydob = [8., 4.]
    gdat.figrsizeydobskin = [8., 2.5]
        
    gdat.listfeatstar = ['radistar', 'massstar', 'tmptstar', 'rascstar', 'declstar', 'vsiistar', 'jmagsyst']
    gdat.listfeatstarpopl = ['radicomp', 'masscomp', 'tmptplan', 'radistar', 'jmagsyst', 'kmagsyst', 'tmptstar']
    
    if gdat.boolplotpopl:
        gdat.liststrgpopl = []
        if gdat.fitt.boolmodlpsys or gdat.boolsimurflx and gdat.true.boolmodlpsys:
            gdat.liststrgpopl += ['exar']
            if gdat.toiitarg is not None:
                gdat.liststrgpopl += ['exof']
        gdat.numbpopl = len(gdat.liststrgpopl)
    
    if gdat.booltserdata and gdat.boolinfe:
        # model
        # type of likelihood
        ## 'sing': assume model is a single realization
        ## 'gpro': assume model is a Gaussian Process (GP)
        if gdat.fitt.typemodlblinshap == 'gpro':
            gdat.typellik = 'gpro'
        else:
            gdat.typellik = 'sing'

    # determine target identifiers
    if gdat.ticitarg is not None:
        gdat.typetarg = 'tici'
        if gdat.typeverb > 0:
            print('A TIC ID was provided as target identifier.')
        
        # check if this TIC is a TOI
        if gdat.fitt.boolmodlpsys or gdat.boolsimurflx and gdat.true.boolmodlpsys:
            indx = np.where(gdat.dictexof['tici'] == gdat.ticitarg)[0]
            if indx.size > 0:
                gdat.toiitarg = int(str(gdat.dictexof['toii'][indx[0]]).split('.')[0])
                if gdat.typeverb > 0:
                    print('Matched the input TIC ID with TOI-%d.' % gdat.toiitarg)
        
        gdat.strgmast = 'TIC %d' % gdat.ticitarg

    elif gdat.toiitarg is not None:
        gdat.typetarg = 'toii'
        if gdat.typeverb > 0:
            print('A TOI ID (%d) was provided as target identifier.' % gdat.toiitarg)
        # determine TIC ID
        gdat.strgtoiibase = str(gdat.toiitarg)
        indx = []
        for k, strg in enumerate(gdat.dictexof['toii']):
            if str(strg).split('.')[0] == gdat.strgtoiibase:
                indx.append(k)
        indx = np.array(indx)
        if indx.size == 0:
            print('Did not find the TOI in the ExoFOP-TESS TOI list.')
            print('gdat.dictexof[TOI]')
            summgene(gdat.dictexof['toii'])
            raise Exception('')
        gdat.ticitarg = gdat.dictexof['tici'][indx[0]]

        if gdat.strgexar is None:
            gdat.strgexar = 'TOI-%d' % gdat.toiitarg
        gdat.strgmast = 'TIC %d' % gdat.ticitarg

    elif gdat.strgmast is not None:
        gdat.typetarg = 'mast'
        if gdat.typeverb > 0:
            print('A MAST key (%s) was provided as target identifier.' % gdat.strgmast)

    elif gdat.rasctarg is not None and gdat.decltarg is not None:
        gdat.typetarg = 'posi'
        if gdat.typeverb > 0:
            print('RA and DEC (%g %g) are provided as target identifier.' % (gdat.rasctarg, gdat.decltarg))
        gdat.strgmast = '%g %g' % (gdat.rasctarg, gdat.decltarg)
    elif gdat.listarrytser is not None:
        gdat.typetarg = 'inpt'

        if gdat.labltarg is None:
            raise Exception('')
    else:
        # synthetic target
        gdat.typetarg = 'synt'

    gdat.numbcompprio = None
    
    # Boolean flag indicating whether MAST has been searched already
    gdat.boolsrchmastdone = False
    
    if (gdat.typetarg == 'tici' or gdat.typetarg == 'toii' or gdat.typetarg == 'mast') and not gdat.boolsrchmastdone and not gdat.boolforcoffl:
        # temp -- check that the closest TIC to a given TIC is itself
        if gdat.typeverb > 0:
            print('Querying the TIC within %s as to get the RA, DEC, Tmag, and TIC ID of the closest source to the MAST keyword %s...' % (gdat.strgradi, gdat.strgmast))
        listdictticinear = astroquery.mast.Catalogs.query_region(gdat.strgmast, radius=gdat.strgradi, catalog="TIC")
        gdat.boolsrchmastdone = True
        if gdat.typeverb > 0:
            print('Found %d TIC sources.' % len(listdictticinear))
        if listdictticinear[0]['dstArcSec'] < 0.2:
            gdat.ticitarg = int(listdictticinear[0]['ID'])
            gdat.rasctarg = listdictticinear[0]['ra']
            gdat.decltarg = listdictticinear[0]['dec']
            gdat.tmagtarg = listdictticinear[0]['Tmag']
    
    print('gdat.typetarg')
    print(gdat.typetarg)
    print('gdat.typetarg')
    print(gdat.typetarg)
    print('gdat.typetarg')
    print(gdat.typetarg)
    print('gdat.boolsrchmastdone')
    print(gdat.boolsrchmastdone)
    print('gdat.boolforcoffl')
    print(gdat.boolforcoffl)
    
    if gdat.typeverb > 0:
        print('gdat.typetarg')
        print(gdat.typetarg)

    if gdat.listtsecinpt is not None and gdat.typetarg != 'inpt':
        raise Exception('List of TESS sectors can only be input when typetarg is "inpt".')
    
    # check if any GPU is available
    import GPUtil
    temp = GPUtil.getGPUs()
    if len(temp) == 0:
        print('No GPU is detected...')

    gdat.maxmnumbiterbdtr = 5
    
    if gdat.typeverb > 0:
        print('gdat.ticitarg')
        print(gdat.ticitarg)
        print('gdat.strgmast')
        print(gdat.strgmast)
        print('gdat.rasctarg')
        print(gdat.rasctarg)
        print('gdat.decltarg')
        print(gdat.decltarg)
        print('gdat.toiitarg')
        print(gdat.toiitarg)
    
    # priors
    if gdat.typepriostar is None:
        if gdat.radistar is not None:
            gdat.typepriostar = 'inpt'
        else:
            gdat.typepriostar = 'tici'
    
    if gdat.booltserdata and gdat.boolinfe:
        if gdat.typeverb > 0:
            if gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'psyspcur':
                print('Stellar parameter prior type: %s' % gdat.typepriostar)
    
    if gdat.booltserdata:
        # number of Boolean signal outputs
        gdat.numbtypeposi = 4
        gdat.indxtypeposi = np.arange(gdat.numbtypeposi)
    
        if gdat.typeverb > 0:
            print('gdat.boolplottser')
            print(gdat.boolplottser)
    
    if gdat.typeverb > 0:
        print('boolplotpopl')
        print(boolplotpopl)
    
    ## NASA Exoplanet Archive
    if gdat.boolplotpopl:
        gdat.dictexar = ephesos.retr_dictexar(strgelem='comp', typeverb=gdat.typeverb)
    
    if gdat.strgclus is None:
        gdat.pathclus = gdat.pathbase
    else:
        #gdat.strgclus += '/'
        if gdat.typeverb > 0:
            print('gdat.strgclus')
            print(gdat.strgclus)
        # data path for the cluster of targets
        gdat.pathclus = gdat.pathbase + '%s/' % gdat.strgclus
        gdat.pathdataclus = gdat.pathclus + 'data/'
        gdat.pathvisuclus = gdat.pathclus + 'visu/'
    
    if gdat.labltarg is None:
        if gdat.typetarg == 'mast':
            gdat.labltarg = gdat.strgmast
        if gdat.typetarg == 'toii':
            gdat.labltarg = 'TOI-%d' % gdat.toiitarg
        if gdat.typetarg == 'tici':
            gdat.labltarg = 'TIC %d' % gdat.ticitarg
        if gdat.typetarg == 'posi':
            gdat.labltarg = 'RA=%.4g, DEC=%.4g' % (gdat.rasctarg, gdat.decltarg)
        if gdat.typetarg == 'synt':
            gdat.labltarg = 'Sim Target'
    
    if gdat.typeverb > 0:
        print('gdat.labltarg')
        print(gdat.labltarg)
    
    # the string that describes the target
    if gdat.strgtarg is None:
        gdat.strgtarg = ''.join(gdat.labltarg.split(' '))
    
    if gdat.booltserdata:
        gdat.lliktemp = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
    
    if gdat.strgcnfg is None:
        if gdat.lablcnfg is None:
            gdat.strgcnfg = ''
        else:
            gdat.strgcnfg = ''.join(gdat.lablcnfg.split(' '))
    
    # the path for the target
    if gdat.pathtarg is None:
        
        gdat.pathtarg = gdat.pathclus + '%s/' % (gdat.strgtarg)
        
        if gdat.strgcnfg is None or gdat.strgcnfg == '':
            strgcnfgtemp = ''
        else:
            strgcnfgtemp = gdat.strgcnfg + '/'
        
        gdat.pathtargruns = gdat.pathtarg + strgcnfgtemp
        
        if gdat.booldiag:
            if gdat.pathtargruns.endswith('//'):
                print('')
                print('')
                print('')
                print('gdat.pathtargruns')
                print(gdat.pathtargruns)
                print('strgcnfgtemp')
                print(strgcnfgtemp)
                raise Exception('')
        
        gdat.pathdatatarg = gdat.pathtargruns + 'data/'
        gdat.pathvisutarg = gdat.pathtargruns + 'visu/'

    if gdat.typeverb > 0:
        print('gdat.strgtarg')
        print(gdat.strgtarg)
    
    # check if the run has been completed before
    path = gdat.pathdatatarg + 'dictmileoutp.pickle'
    if not gdat.boolwritover and os.path.exists(path):
        
        if gdat.typeverb > 0:
            print('Reading from %s...' % path)
        with open(path, 'rb') as objthand:
            gdat.dictmileoutp = pickle.load(objthand)
        
        return gdat.dictmileoutp

    if gdat.strgtarg == '' or gdat.strgtarg is None or gdat.strgtarg == 'None' or len(gdat.strgtarg) == 0:
        raise Exception('')
    
    for name in ['strgtarg', 'pathtarg']:
        gdat.dictmileoutp[name] = getattr(gdat, name)

    if gdat.booltserdata:
        
        if gdat.listener is None:
            gdat.listener = [[] for p in gdat.indxinst[0]]
        else:
            if gdat.booldiag:
                if np.isscalar(gdat.listener[0]):
                    print('')
                    print('gdat.listener should be a list of arrays.')
                    print('gdat.listener')
                    print(gdat.listener)
                    raise Exception('')
        
        if gdat.typeverb > 0:
            print('gdat.numbinst')
            print(gdat.numbinst)
            print('gdat.strgcnfg')
            print(gdat.strgcnfg)
            print('gdat.liststrginst')
            print(gdat.liststrginst)
        
        if gdat.booldiag:
            if gdat.strgcnfg == '_':
                print('')
                print('')
                print('')
                raise Exception('')

        gdat.pathalle = dict()
        gdat.objtalle = dict()
        
    if gdat.booltserdata:
        
        # Boolean flag to execute a search for flares
        if gdat.boolsrchflar is None:
            if gdat.boolinfe and gdat.fitt.typemodl == 'flar':
                gdat.boolsrchflar = True
            else:
                gdat.boolsrchflar = False
        
        if gdat.typeverb > 0:
            print('gdat.boolsimurflx')
            print(gdat.boolsimurflx)
            print('gdat.boolretrlcurmast')
            print(gdat.boolretrlcurmast)
        
        if gdat.boolretrlcurmast:
            #if gdat.boolsimurflx:
            #    gdat.dictretrlcurinpt['strgtypedata'] = 'simugenelcur'
            #else:
            #    gdat.dictretrlcurinpt['strgtypedata'] = 'obsd'
            gdat.dictlygoinpt['pathtarg'] = gdat.pathtargruns + 'lygos/'
            
            #if gdat.liststrginst is None:
            #    gdat.liststrginst = ['TESS', 'Kepler', 'K2', 'JWST_NIRSpec']
            print('liststrginst')
            print(liststrginst)
            
            if not 'liststrginst' in gdat.dictlygoinpt:
                gdat.dictlygoinpt['liststrginst'] = gdat.liststrginst[0]
            
            if not 'typepsfninfe' in gdat.dictlygoinpt:
                gdat.dictlygoinpt['typepsfninfe'] = 'fixd'
                #gdat.dictlygoinpt['maxmradisrchmast'] = maxmradisrchmast
            
            maxmradisrchmast = 10. # arcsec
            strgradi = '%gs' % maxmradisrchmast
            
            gdat.pathdatamast = os.environ['MAST_DATA_PATH'] + '/'
            os.system('mkdir -p %s' % gdat.pathdatamast)
            
            # determine the MAST keyword to be used for the target
            if gdat.strgmast is not None:
                strgmasttemp = gdat.strgmast
            elif rasctarg is not None:
                strgmasttemp = '%g %g' % (rasctarg, decltarg)
            elif gdat.ticitarg is not None:
                strgmasttemp = 'TIC %d' % gdat.ticitarg
                
            if gdat.strgmast is not None or gdat.ticitarg is not None or rasctarg is not None:
                # get the list of sectors for which TESS FFI data are available via TESSCut
                gdat.listtsectcut, temp, temp = retr_listtsectcut(strgmasttemp)
            
                print('List of TESS sectors for which FFI data are available via TESSCut:')
                print(gdat.listtsectcut)
            
            if gdat.boolutiltesslocl:
                # determine the TIC ID to be used for the MAST search
                ticitsec = None
                if gdat.ticitarg is None:
                    print('Will determine the TIC ID of the target using MAST keyword %s.' % strgmasttemp)
                    print('Querying the TIC for sources within %s of %s...' % (strgradi, strgmasttemp))
                    listdictticinear = astroquery.mast.Catalogs.query_object(strgmasttemp, catalog='TIC', radius=strgradi)
                    if len(listdictticinear) > 0 and listdictticinear[0]['dstArcSec'] < 1.:
                        print('TIC associated with the search is %d' % ticitsec)
                        ticitsec = int(listdictticinear[0]['ID'])
                    else:
                        print('Warning! No TIC match to the MAST keyword: %s' % strgmasttemp)
                
                # get the list of sectors for which TESS SPOC data are available
                listtsec2min, listpathdisk2min = retr_tsecpathlocl(ticitsec)
                print('List of TESS sectors for which SPOC data are available for the TIC ID %d:' % ticitsec)
                print(listtsec2min)
            
            # get observation tables
            listpathdownspoc = []
            if typeverb > 0:
                print('Querying the MAST for observation tables with MAST keyword %s within %g arcseconds...' % (strgmasttemp, maxmradisrchmast))
            listtablobsv = astroquery.mast.Observations.query_object(strgmasttemp, radius=strgradi)
            print('Found %d tables...' % len(listtablobsv))
            listname = list(listtablobsv.keys())
            
            print('gdat.listener')
            print(gdat.listener)
            gdat.liststrginstfinl = []
            for strgexpr in gdat.liststrginst[0]:
                if not (strgexpr == 'TESS' and gdat.boolutiltesslocl):
                    gdat.liststrginstfinl.append(strgexpr)
            
            gdat.listarrylcurmast = [[] for strgexpr in gdat.liststrginst[0]]
            
            #print('listtablobsv')
            #for name in listname:
            #    print(name)
            #    summgene(listtablobsv[name].value, boolshowuniq=True)
            #    print('')

            print('listname')
            print(listname)
            for mm, strgexpr in enumerate(gdat.liststrginstfinl):
                if strgexpr.startswith('JWST'):
                    strgexprtemp = 'JWST'
                    strgexprsubb = strgexpr[5:]
                    if 'g395h' in strgexprsubb:
                        strgexprdete = strgexprsubb[-4:]
                        strgexprsubb = strgexprsubb[:-5]
                else:
                    strgexprtemp = strgexpr
                
                print('strgexpr')
                print(strgexpr)
                print('strgexprtemp')
                print(strgexprtemp)

                #indx = np.where((listtablobsv['obs_collection'] == strgexprtemp) & (listtablobsv['dataproduct_type'] == 'timeseries'))
                boolgood = (listtablobsv['obs_collection'] == strgexprtemp)
                # & (listtablobsv['dataproduct_type'] == 'timeseries'))

                if strgexprtemp == 'TESS':
                    
                    if gdat.typelcurtpxftess == 'lygos' or gdat.boolffimonly:
                        continue

                    gdat.listtsecspoc = []
                    #print('gdat.ticitarg')
                    #print(gdat.ticitarg)
                    #print('type(gdat.ticitarg)')
                    #print(type(gdat.ticitarg))
                    #print('%s % gdat.ticitarg')
                    #print('%s' % gdat.ticitarg)
                    #print('listtablobsv[target_name].value')
                    #print(listtablobsv['target_name'].value)
                    #print('np.unique(listtablobsv[target_name].value)')
                    #print(np.unique(listtablobsv['target_name'].value))
                    #summgene(listtablobsv['target_name'].value)
                    #print('')
                    
                    if gdat.booldiag:
                        if gdat.ticitarg is None:
                            print('')
                            print('')
                            print('')
                            print('gdat.ticitarg is None')
                            raise Exception('')
                    
                    boolgood = boolgood & (listtablobsv['target_name'].value == '%s' % gdat.ticitarg)
                    
                if strgexprtemp == 'K2':
                    boolgood = boolgood & (listtablobsv['dataproduct_type'] == 'timeseries') & (listtablobsv['target_name'] == gdat.strgmast)
                
                if strgexprtemp == 'JWST':
                    boolgood = boolgood & (listtablobsv['provenance_name'] == 'CALJWST') & \
                               (listtablobsv['target_name'] == gdat.strgmast) & \
                               (listtablobsv['calib_level'] == 3) & \
                               (listtablobsv['dataRights'] == 'PUBLIC')
                               #(listtablobsv['obs_id'] == strgexpr[5:]) & \
                    
                    boolgoodtemp = np.empty_like(boolgood)
                    for ll in range(len(boolgoodtemp)):
                        boolgoodtemp[ll] = strgexpr[5:] in listtablobsv['obs_id'][ll]
                    boolgood = boolgood & boolgoodtemp

                indx = np.where(boolgood)[0]

                #print('indx')
                #print(indx)
                #print('listtablobsv')
                #print(listtablobsv)

                print('%d tables...' % len(listtablobsv[indx]))
                
                if strgexprtemp == 'K2':
                    #print('K2 chunks')
                    for obid in listtablobsv['obs_id'][indx]:
                        strgchun = obid.split('-')
                        #print('obid')
                        #print(obid)
                        #print('strgchun')
                        #print(strgchun)
                        #if len(strgchun) > 1:# and strgchun[1] != '':
                        #    listtsec2min.append(int(strgchun[1][1:3]))
                        #    #listpath2min

                listname = list(listtablobsv[indx].keys())
                
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('')
                #print('listtablobsv')
                #for name in listname:
                #    print(name)
                #    summgene(listtablobsv[name].value, boolshowuniq=True)
                #    print('')
                #
                #print('listname')
                #print(listname)
                #print('len(listname)')
                #print(len(listname))
                
                cntrtess = 0

                gdat.listpathspocmast = []
                
                if indx.size > 0:
                    print('Will get the list of products for each table...')
                
                for k, tablobsv in enumerate(listtablobsv[indx]):
                
                    if listtablobsv['distance'][k] > 0:
                        print('Distance of table number %d: %g' % (k, listtablobsv['distance'][k]))
                        continue
                    
                    print('Table %d...' % k)
                    print('Getting the product list for table %d...' % k)
                    listprod = astroquery.mast.Observations.get_product_list(tablobsv)
                    numbprod = len(listprod)
                    print('numbprod')
                    print(numbprod)

                    listname = list(listprod.keys())
                    
                    #print('listname')
                    #print(listname)
                    #print('listprod')
                    #for name in listname:
                    #    print(name)
                    #    summgene(listprod[name].value, boolshowuniq=True)
                    #    print('')
                    
                    boolgood = np.ones(numbprod, dtype=bool)
                    if strgexprtemp == 'JWST' or strgexprtemp == 'TESS':
                        boolgoodtemp = np.empty(numbprod, dtype=bool)
                        for kk in range(numbprod):
                            if strgexprtemp == 'JWST':
                                boolgoodtemp[kk] = listprod[kk]['productFilename'].endswith('_x1dints.fits') and strgexprsubb in listprod[kk]['productFilename'] and \
                                                                                                        not '-seg' in listprod[kk]['productFilename']
                        
                            if strgexprtemp == 'TESS':
                                # choose lc.fits instead of tp.fits
                                boolgoodtemp[kk] = listprod[kk]['productFilename'].endswith('lc.fits')
                        
                        #print((listprod['productSubGroupDescription'].value == 'S2D').dtype)
                        #print('listprod[productSubGroupDescription].value == S2D')
                        #print(listprod['productSubGroupDescription'].value == 'S2D')
                        #summgene(listprod['productSubGroupDescription'].value == 'S2D')
                        #print('listprod[productSubGroupDescription].value == X1D')
                        #print(listprod['productSubGroupDescription'].value == 'X1D')
                        #summgene(listprod['productSubGroupDescription'].value == 'X1D')
                        #boolgoodtemp = (listprod['productSubGroupDescription'].value == 'S2D' | listprod['productSubGroupDescription'].value == 'X1D')
                        #boolgoodtemp = (listprod['productSubGroupDescription'] == 'S2D' | listprod['productSubGroupDescription'] == 'X1D')
                        #print('boolgood')
                        #summgene(boolgood)
                        boolgood = boolgood & boolgoodtemp
                    
                    indxprodgood = np.where(boolgood)[0]
                    if indxprodgood.size > 1:
                        if strgexprtemp == 'JWST':
                            print('')
                            print('')
                            print('')
                            print('More than one good product.')
                            for kk in range(indxprodgood.size):
                                print('listprod[indxprodgood[kk]][productFilename]')
                                print(listprod[indxprodgood[kk]]['productFilename'])
                            print('indxprodgood')
                            print(indxprodgood)
                            raise Exception('')
                    #print('indxprodgood')
                    #summgene(indxprodgood)

                
                    #print('listprod')
                    #for name in listname:
                    #    print(name)
                    #    summgene(listprod[name], boolshowuniq=True)
                    #    print('')
                    #print('')
                    #if strgexpr == 'TESS':
                    #    print('listprod')
                    #    print(listprod)
                    #    for a in range(len(listprod)):
                    #        print('listprod[a]')
                    #        print(listprod[a])
                    #        boolfasttemp = listprod[a]['obs_id'].endswith('fast')
                    #        if not boolfasttemp:
                    #            tsec = int(listprod[a]['obs_id'].split('-')[1][1:])

                    print('Downloading products for table number %d...' % k)
                    # download data from MAST
                    manifest = astroquery.mast.Observations.download_products(listprod[indxprodgood], download_dir=gdat.pathdatamast)
                    print('indxprodgood')
                    summgene(indxprodgood)
                    
                    if manifest is not None:
                        for path in manifest['Local Path']:
                            print('path')
                            print(path)
                            listhdun = astropy.io.fits.open(path)
                            listhdun.info()
                                
                            #'jw01366-o004_t001_nirspec_clear-prism-s1600a1-sub512_x1dints.fits'
                            #if path.endswith('allslits_x1d.fits') or path.endswith('s1600a1_x1d.fits') or 
                            
                            if 'tess' in path:
                                gdat.listpathspocmast.append(path)
                                arrylcur, tsec, tcam, tccd = \
                                    ephesos.read_tesskplr_file(path, typeinst='tess', strgtypelcur='PDCSAP_FLUX', \
                                                                             booldiag=gdat.booldiag, boolmaskqual=gdat.boolmaskqual, boolnorm=gdat.boolnormphot)
                                
                                gdat.listtsecspoc.append(tsec)
                                gdat.listarrylcurmast[mm].append(arrylcur[:, None, :])
                                print('cntrtess')
                                print(cntrtess)
                            elif 'niriss' in path or path.endswith('nis_x1dints.fits'):
                                pass
                                #listtime = listhdun['EXTRACT1D'].data
                                #wlen = listhdun[1].data['WAVELENGTH']
                                #print(listhdun[1].data.names)
                                #print('wlen')
                                #summgene(wlen)
                                #numbtime = len(listhdun[1].data)
                                #arry = np.empty((numbwlen, numbtime))
                                #indxtime = np.arange(numbtime)
                                #arry = listhdun[1].data['FLUX']
                                #print('arry')
                                #summgene(arry)
                            else:
                                
                                listtime = listhdun['INT_TIMES'].data
                                listhdun.info()
                                #print('listtime')
                                #print(listtime)
                                #summgene(listtime)
                                numbtime = len(listtime)
                                if 'g395h' in strgexprsubb:
                                    if strgexprdete == 'NRS1':
                                        wlen = listhdun[2].data['WAVELENGTH']
                                    if strgexprdete == 'NRS2':
                                        wlen = listhdun[-1].data['WAVELENGTH']
                                else:
                                    wlen = listhdun[2].data['WAVELENGTH']
                                    
                                numbwlen = wlen.size
                                gdat.listener[mm] = wlen
                                arry = np.empty((numbtime, numbwlen, 3))
                                
                                print('listhdun[2].data.names')
                                print(listhdun[2].data.names)
                                
                                print('numbwlen')
                                print(numbwlen)
                                if not path.endswith('.fits'):
                                    raise Exception('')

                                pathmile = path[:-5] + '_mile.npy'
                                if os.path.exists(pathmile):
                                    print('Reading from %s...' % pathmile)
                                    arry = np.load(pathmile)
                                else:
                                    numbener = np.empty(numbtime)
                                    for t in tqdm(range(numbtime)):
                                        arry[t, 0, 0] = np.mean(listtime[t][1:]) + 2400000
                                        numbener[t] = listhdun[t+2].data['WAVELENGTH'].size
                                        print('numbener[t]')
                                        print(numbener[t])
                                        #print('')
                                        #print('listhdun[%d+2].data[WAVELENGTH]' % t)
                                        #summgene(listhdun[t+2].data['WAVELENGTH'])
                                        #print('listhdun[%d+2].data[FLUX]' % t)
                                        #summgene(listhdun[t+2].data['FLUX'])
                                        #print('listhdun[%d+2].data[FLUX_ERROR]' % t)
                                        #summgene(listhdun[t+2].data['FLUX_ERROR'])
                                        
                                        if gdat.booldiag:
                                            if listhdun[t+2].data['FLUX'].ndim != 1:
                                                print('')
                                                print('')
                                                print('')
                                                print('listhdun[t+2].data[FLUX] should be one dimensional')
                                                print('listhdun[t+2].data[FLUX]')
                                                summgene(listhdun[t+2].data['FLUX'])
                                                raise Exception('')
                                        
                                        if listhdun[t+2].data['FLUX'].size == numbwlen:
                                            arry[t, :, 1] = listhdun[t+2].data['FLUX']
                                            arry[t, :, 2] = listhdun[t+2].data['FLUX_ERROR']
                                    print('Writing to %s...' % pathmile)
                                    np.save(pathmile, arry)
                                print('arry[:, :, 0]')
                                summgene(arry[:, :, 0])
                                print('arry[:, :, 1]')
                                summgene(arry[:, :, 1])
                                print('arry[:, :, 2]')
                                summgene(arry[:, :, 2])
                                gdat.listarrylcurmast[mm] = [arry]

                            print('')
                            print('')
                            print('')
                    cntrtess += 1
                print('')
                print('')
                print('')
                
                if strgexprtemp == 'TESS':
                    gdat.listtsecspoc = np.array(gdat.listtsecspoc, dtype=int)
            
            print('gdat.boolutiltesslocl')
            print(gdat.boolutiltesslocl)

            booltess = 'TESS' in gdat.liststrginst[0]
            booltesskepl = 'Kepler' in gdat.liststrginst[0] or 'TESS' in gdat.liststrginst[0] or 'K2' in gdat.liststrginst[0]
            if booltesskepl:
                if gdat.typelcurtpxftess == 'lygos' or gdat.boolffimonly:
                    gdat.listtseclygo = gdat.listtsectcut
                    gdat.listtsecspoc = np.array([], dtype=int)
                else:
                    gdat.listtseclygo = np.setdiff1d(gdat.listtsectcut, gdat.listtsecspoc)

                print('List of chunks to be reduced via lygos')
                print(gdat.listtseclygo)
                print('List of chunks to be taken from SPOC')
                print(gdat.listtsecspoc)
                
                numbtsecspoc = gdat.listtsecspoc.size
                indxtsecspoc = np.arange(numbtsecspoc)

            if booltess:
                print('gdat.typelcurtpxftess')
                print(gdat.typelcurtpxftess)
            
                gdat.listtsecpdcc = np.empty_like(gdat.listtsecspoc)
                gdat.listtsecsapp = np.empty_like(gdat.listtsecspoc)

                # merge list of sectors whose light curves will come from SPOC and lygos, respectively
                gdat.listtsec = np.unique(np.concatenate((gdat.listtseclygo, gdat.listtsecspoc), dtype=int))

                print('List of TESS sectors')
                print(gdat.listtsec)
            
            # filter the list of sectors using the desired list of sectors, if any
            if listtsecsele is not None:
                print('Filtering the list of sectors based on the user selection (listtsecsele)...')
                listtsecsave = np.copy(gdat.listtsec)
                gdat.listtsec = []
                for tsec in listtsecsele:
                    if tsec in listtsecsave:
                        gdat.listtsec.append(tsec)
                
                gdat.listtsec = np.array(gdat.listtsec, dtype=int)
            
                print('Filtered list of TESS sectors')
                print(gdat.listtsec)
            
            if gdat.booldiag:
                for b in gdat.indxdatatser:
                    for p in gdat.indxinst[b]:
                        if b == 0 and gdat.liststrginst[b][p] == 'TESS' and len(gdat.listtsecspoc) != len(gdat.listarrylcurmast[p]):
                            print('')
                            print('')
                            print('')
                            print('len(gdat.listarrylcurmast[p]) should match the length of gdat.listtsec.')
                            print('len(gdat.listarrylcurmast[p])')
                            print(len(gdat.listarrylcurmast[p]))
                            print('gdat.listarrylcurmast[p]')
                            print(gdat.listarrylcurmast[p])
                            print('gdat.listtsec')
                            print(gdat.listtsec)
                            summgene(gdat.listtsec)
                            print('gdat.listtsecspoc')
                            print(gdat.listtsecspoc)
                            summgene(gdat.listtsecspoc)
                            raise Exception('')

            if booltess:
                numbtsec = len(gdat.listtsec)
                indxtsec = np.arange(numbtsec)

                listtcam = np.empty(numbtsec, dtype=int)
                listtccd = np.empty(numbtsec, dtype=int)
            
                # determine for each sector whether a TFP is available
                booltpxf = ephesos.retr_booltpxf(gdat.listtsec, gdat.listtsecspoc)
            
                if typeverb > 0:
                    print('booltpxf')
                    print(booltpxf)
                
                if gdat.typelcurtpxftess == 'lygos':
                    boollygo = np.ones(numbtsec, dtype=bool)
                    booltpxflygo = not gdat.boolffimonly
                    gdat.listtseclygo = gdat.listtsec
                if gdat.typelcurtpxftess == 'SPOC':
                    boollygo = ~booltpxf
                    booltpxflygo = False
                    gdat.listtseclygo = gdat.listtsec[boollygo]
                gdat.listtseclygo = gdat.listtsec[boollygo]
                
                print('boollygo')
                print(boollygo)
                print('gdat.boolffimonly')
                print(gdat.boolffimonly)
                print('booltpxflygo')
                print(booltpxflygo)

                if typeverb > 0:
                    print('booltpxflygo')
                    print(booltpxflygo)
                    print('gdat.listtseclygo')
                    print(gdat.listtseclygo)
            
            gdat.dictlygooutp = None

            if booltess and len(gdat.listtseclygo) > 0:
                
                if gdat.typetarg == 'mast':
                    gdat.dictlygoinpt['strgmast'] = gdat.strgmast
                elif gdat.typetarg == 'tici' or gdat.typetarg == 'toii':
                    gdat.dictlygoinpt['ticitarg'] = gdat.ticitarg
                elif gdat.typetarg == 'posi':
                    gdat.dictlygoinpt['rasctarg'] = rasctarg
                    gdat.dictlygoinpt['decltarg'] = decltarg
                else:
                    raise Exception('')
                gdat.dictlygoinpt['labltarg'] = labltarg
                gdat.dictlygoinpt['listipntsele'] = gdat.listtseclygo
                gdat.dictlygoinpt['booltpxflygo'] = booltpxflygo
                gdat.dictlygoinpt['listnameanls'] = 'psfn'
                if not 'boolmaskqual' in gdat.dictlygoinpt:
                    gdat.dictlygoinpt['boolmaskqual'] = gdat.boolmaskqual
                
                # Boolean flag to make lygos normalize the light curve by the median
                if not 'boolnorm' in gdat.dictlygoinpt:
                    gdat.dictlygoinpt['boolnorm'] = True
                
                if typeverb > 0:
                    print('Will run lygos on the target...')
                gdat.dictlygooutp = lygos.main.init( \
                                               **gdat.dictlygoinpt, \
                                              )
                
                for o, tseclygo in enumerate(gdat.listtsec):
                    indx = np.where(gdat.dictlygooutp['listtsec'][0] == tseclygo)[0]
                    if indx.size > 0:
                        indxtsecthis = indx[0]
                        if len(gdat.dictlygooutp['arryrflx'][nameanlslygo][0][indxtsecthis]) > 0:
                            
                            # choose the current sector
                            arry = gdat.dictlygooutp['arryrflx'][nameanlslygo][0][indxtsecthis]
                            
                            # find good times
                            indxtimegood = np.where(np.isfinite(arry[:, 1]) & np.isfinite(arry[:, 2]))[0]
                            
                            # filter for good times
                            gdat.listarrylcurmast[p][o] = arry[indxtimegood, :]
                            
                            listtcam[o] = gdat.dictlygooutp['listtcam'][indxtsecthis]
                            listtccd[o] = gdat.dictlygooutp['listtccd'][indxtsecthis]
            
            gdat.listarrylcurmastsapp = None
            gdat.listarrylcurmastpdcc = None
            arrylcursapp = None
            arrylcurpdcc = None
            
            
            if booltesskepl:
                # make sure the list of paths to sector files are time-sorted
                #listpathdown.sort()
                
                if len(gdat.listtsecspoc) > 0 and gdat.typelcurtpxftess == 'SPOC':
                    
                    ## read SPOC light curves
                    gdat.listarrylcurmastsapp = [[] for o in indxtsec] 
                    gdat.listarrylcurmastpdcc = [[] for o in indxtsec] 
                    for o in indxtsec:
                        if not boollygo[o]:
                            
                            indx = np.where(gdat.listtsec[o] == gdat.listtsecspoc)[0][0]
                            path = gdat.listpathspocmast[indx]
                            if typeverb > 0:
                                print('Reading the SAP light curves...')
                            gdat.listarrylcurmastsapp[o], gdat.listtsecsapp[o], listtcam[o], listtccd[o] = \
                                                   ephesos.read_tesskplr_file(path, typeinst='tess', strgtypelcur='SAP_FLUX', \
                                                                                booldiag=gdat.booldiag, boolmaskqual=gdat.boolmaskqual, boolnorm=gdat.boolnormphot)
                            if typeverb > 0:
                                print('Reading the PDC light curves...')
                            gdat.listarrylcurmastpdcc[o], gdat.listtsecpdcc[o], listtcam[o], listtccd[o] = \
                                                   ephesos.read_tesskplr_file(path, typeinst='tess', strgtypelcur='PDCSAP_FLUX', \
                                                                                booldiag=gdat.booldiag, boolmaskqual=gdat.boolmaskqual, boolnorm=gdat.boolnormphot)
                            
                            # to be deleted
                            #if typedataspoc == 'SAP':
                            #    arrylcur = gdat.listarrylcurmastsapp[o]
                            #else:
                            #    arrylcur = gdat.listarrylcurmastpdcc[o]
                            #gdat.listarrylcurmast[p][o] = arrylcur
                            #if booldiag:
                            #    if not np.isfinite(arrylcur).all():
                            #        print('')
                            #        print('')
                            #        print('')
                            #        print('gdat.boolmaskqual')
                            #        print(gdat.boolmaskqual)
                            #        print('arrylcur')
                            #        summgene(arrylcur)
                            #        raise Exception('')

                    # merge light curves from different sectors
                    arrylcursapp = np.concatenate([arry for arry in gdat.listarrylcurmastsapp if len(arry) > 0], 0)
                    arrylcurpdcc = np.concatenate([arry for arry in gdat.listarrylcurmastpdcc if len(arry) > 0], 0)
            
            if typeverb > 0:
                if booltess:
                    if numbtsec > 0:
                        if numbtsec == 1:
                            strgtemp = ''
                        else:
                            strgtemp = 's'
                        print('%d sector%s of data retrieved.' % (numbtsec, strgtemp))
                        print('gdat.listtsec')
                        print(gdat.listtsec)
            
            # check if gdat.listarrylcurmast contains any empty sectors and remove from gdat.listarrylcurmast, listtcam, listtccd, and gdat.listtsec
            for p in gdat.indxinst[b]:
                boolbadd = False
                for arrylcur in gdat.listarrylcurmast[p]:
                    if len(arrylcur) == 0:
                        boolbadd = True
                if boolbadd:
                    if typeverb > 0:
                        print('gdat.listarrylcurmast contains at least one empty element (i.e., sector with no data). Will remove all such elements.')
                    listarrylcurmasttemp = []
                    listindxtsecgood = []
                    for o in indxtsec:
                        if len(gdat.listarrylcurmast[p][o]) > 0:
                            listindxtsecgood.append(o)
                    listindxtsecgood = np.array(listindxtsecgood, dtype=int)
                    gdat.listtsec = gdat.listtsec[listindxtsecgood]
                    listtcam = listtcam[listindxtsecgood]
                    listtccd = listtccd[listindxtsecgood]
                    for indxtsecgood in listindxtsecgood:
                        listarrylcurmasttemp.append(gdat.listarrylcurmast[p][indxtsecgood, :, :])
                    gdat.listarrylcurmast[p] = listarrylcurmasttemp
                
            if gdat.booldiag:
                for b in gdat.indxdatatser:
                    for p in gdat.indxinst[b]:
                        if b == 0 and gdat.liststrginst[b][p] == 'TESS' and len(gdat.listtsecspoc) != len(gdat.listarrylcurmast[p]):
                            print('')
                            print('')
                            print('')
                            print('len(gdat.listarrylcurmast[p]) should match the length of gdat.listtsec.')
                            print('gdat.listarrylcurmast[p]')
                            print(gdat.listarrylcurmast[p])
                            print('gdat.listtsec')
                            print(gdat.listtsec)
                            raise Exception('')

            if booltess:
                gdat.dictmileoutp['listtsec'] = gdat.listtsec
                print('List of TESS sectors:')
                print(gdat.listtsec)
            
            if gdat.dictlygooutp is not None:
                for name in gdat.dictlygooutp:
                    gdat.dictmileoutp['lygo_' + name] = gdat.dictlygooutp[name]
            
        if gdat.boolsimurflx:
            
            print('gdat.listener')
            print(gdat.listener)
            gdat.indxener = [[] for p in gdat.indxinst[0]]
            for p in gdat.indxinst[0]:
                if gdat.listener[p] is not None and len(gdat.listener[p]) > 0:
                    print('gdat.listener[p]')
                    print(gdat.listener[p])
                    gdat.numbener[p] = gdat.listener[p].size
                else:
                    gdat.numbener[p] = 1
                print('p')
                print(p)
                print('gdat.numbener')
                print(gdat.numbener)
                print('gdat.listener')
                print(gdat.listener)
                gdat.indxener[p] = np.arange(gdat.numbener[p])
            
            tdpy.setp_para_defa(gdat, 'true', 'typemodl', 'psys')

            tdpy.setp_para_defa(gdat, 'true', 'typemodlsupn', 'quad')
            tdpy.setp_para_defa(gdat, 'true', 'typemodlexcs', 'bump')

            setp_modlinit(gdat, 'true')

        else:
            gdat.numbener[p] = 1
        
        print('gdat.liststrginst')
        print(gdat.liststrginst)
        print('gdat.listarrylcurmast')
        print(gdat.listarrylcurmast)
        if gdat.strgtarg == 'WASP-43':
            raise Exception('')

        if gdat.boolinfe and gdat.fitt.boolmodlpsys or gdat.boolsimurflx and gdat.true.boolmodlpsys:
            if gdat.strgexar is None:
                gdat.strgexar = gdat.strgmast
    
            if gdat.typeverb > 0:
                print('gdat.strgexar')
                print(gdat.strgexar)

            # grab object features from NASA Excoplanet Archive
            gdat.dictexartarg = ephesos.retr_dictexar(strgexar=gdat.strgexar, strgelem='comp', typeverb=gdat.typeverb)
            
            if gdat.typeverb > 0:
                if gdat.dictexartarg is None:
                    print('The target name was **not** found in the NASA Exoplanet Archive planetary systems composite table.')
                else:
                    print('The target name was found in the NASA Exoplanet Archive planetary systems composite table.')
            
            # grab object features from ExoFOP
            if gdat.toiitarg is not None:
                gdat.dictexoftarg = ephesos.retr_dicttoii(toiitarg=gdat.toiitarg)
            else:
                gdat.dictexoftarg = None
            gdat.boolexof = gdat.toiitarg is not None and gdat.dictexoftarg is not None
            gdat.boolexar = gdat.strgexar is not None and gdat.dictexartarg is not None or gdat.typepriocomp == 'exar'
            
            if gdat.typepriocomp is None:
                if gdat.epocmtracompprio is not None:
                    gdat.typepriocomp = 'inpt'
                elif gdat.boolexar:
                    gdat.typepriocomp = 'exar'
                elif gdat.boolexof:
                    gdat.typepriocomp = 'exof'
                else:
                    gdat.typepriocomp = 'pdim'

            if gdat.typeverb > 0:
                print('Companion prior type (typepriocomp): %s' % gdat.typepriocomp)
            
            if not gdat.boolexar and gdat.typepriocomp == 'exar':
                raise Exception('')
    
        ## list of analysis types
        ### 'pdim': search for periodic dimmings
        ### 'pinc': search for periodic increases
        ### 'lspe': search for sinusoid variability
        ### 'mfil': matched filter
        if gdat.listtypeanls is None:
            gdat.listtypeanls = ['lspe']
        if gdat.boolinfe and (gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'psyspcur') and gdat.typepriocomp == 'pdim':
            gdat.listtypeanls += ['pdim']
        if gdat.boolinfe and gdat.fitt.typemodl == 'cosc':
            gdat.listtypeanls += ['pinc']

        if gdat.typeverb > 0:
            print('List of analysis types: %s' % gdat.listtypeanls)
        
        if gdat.boolbdtr is None:
            
            gdat.boolbdtr = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if gdat.boolinfe and (gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'psyspcur') and not gdat.liststrginst[b][p].startswith('LSST'):
                        gdat.boolbdtr[b][p] = True
                    else:
                        gdat.boolbdtr[b][p] = False
        
        gdat.boolbdtranyy = False
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if gdat.boolbdtr[b][p]:
                    gdat.boolbdtranyy = True
        
        ## Boolean flag to calculate the power spectral density
        gdat.boolcalclspe = 'lspe' in gdat.listtypeanls

        # Boolean flag to execute a search for periodic boxes
        gdat.boolsrchpdim = 'pdim' in gdat.listtypeanls

        # Boolean flag to execute a search for periodic boxes
        gdat.boolsrchpinc = 'pinc' in gdat.listtypeanls
        
        gdat.boolsrchpbox = gdat.boolsrchpinc or gdat.boolsrchpdim

        if gdat.typeverb > 0:
            print('gdat.boolcalclspe') 
            print(gdat.boolcalclspe)
            print('gdat.boolsrchpdim') 
            print(gdat.boolsrchpdim)
            print('gdat.boolsrchpinc') 
            print(gdat.boolsrchpinc)
            print('gdat.boolsrchpbox') 
            print(gdat.boolsrchpbox)
            print('gdat.boolsrchflar') 
            print(gdat.boolsrchflar)
        
        if gdat.typeverb > 0:
            print('gdat.boolplotpopl')
            print(gdat.boolplotpopl)
        
        gdat.liststrgpdfn = ['prio']
        
    if gdat.boolplotpopl:
        ## define folders
        gdat.pathvisufeat = gdat.pathvisutarg + 'feat/'
    
        for strgpdfn in ['prio']:
            pathvisupdfn = gdat.pathvisufeat + strgpdfn + '/'
            setattr(gdat, 'pathvisufeatplan' + strgpdfn, pathvisupdfn + 'featplan/')
            setattr(gdat, 'pathvisufeatsyst' + strgpdfn, pathvisupdfn + 'featsyst/')
            setattr(gdat, 'pathvisudataplan' + strgpdfn, pathvisupdfn + 'dataplan/')
    
    ## make folders
    for attr, valu in gdat.__dict__.items():
        if attr.startswith('path') and valu is not None and not isinstance(valu, dict) and valu.endswith('/'):
            os.system('mkdir -p %s' % valu)
            
    gdat.duraprio = None
    
    if gdat.booltserdata:
        
        if gdat.boolinfe and gdat.fitt.boolmodlpsys or gdat.boolsimurflx and gdat.true.boolmodlpsys:
        
            if gdat.typepriocomp == 'exar':
                gdat.pericompprio = gdat.dictexartarg['pericomp']
                gdat.rsmacompprio = gdat.dictexartarg['rsmacomp']
                gdat.rratcompprio = gdat.dictexartarg['rratcomp']
                gdat.deptprio = gdat.dictexartarg['depttrancomp']
                gdat.cosicompprio = gdat.dictexartarg['cosicomp']
                gdat.epocmtracompprio = gdat.dictexartarg['epocmtracomp']

                gdat.duraprio = gdat.dictexartarg['duratrantotl']
                indx = np.where(~np.isfinite(gdat.duraprio) & gdat.dictexartarg['booltran'])[0]
                if indx.size > 0:
                    dcyc = 0.15
                    if gdat.typeverb > 0:
                        print('Duration from the Exoplanet Archive Composite PS table is infite for companions. Assuming a duty cycle of %.3g.' % dcyc)
                    gdat.duraprio[indx] = gdat.pericompprio[indx] * dcyc
            if gdat.typepriocomp == 'exof':
                if gdat.typeverb > 0:
                    print('A TOI ID is provided. Retreiving the TCE attributes from ExoFOP-TESS...')
                
                if gdat.epocmtracompprio is None:
                    gdat.epocmtracompprio = gdat.dictexoftarg['epocmtracomp']
                if gdat.pericompprio is None:
                    gdat.pericompprio = gdat.dictexoftarg['pericomp']
                gdat.deptprio = gdat.dictexoftarg['depttrancomp']
                gdat.duraprio = gdat.dictexoftarg['duratrantotl']
                if gdat.cosicompprio is None:
                    gdat.cosicompprio = np.zeros_like(gdat.epocmtracompprio)

            if gdat.typepriocomp == 'inpt':
                if gdat.rratcompprio is None:
                    gdat.rratcompprio = 0.1 + np.zeros_like(gdat.epocmtracompprio)
                if gdat.rsmacompprio is None:
                    gdat.rsmacompprio = 0.2 * gdat.pericompprio**(-2. / 3.)
                
                if gdat.typeverb > 0:
                    print('gdat.cosicompprio')
                    print(gdat.cosicompprio)

                if gdat.cosicompprio is None:
                    gdat.cosicompprio = np.zeros_like(gdat.epocmtracompprio)
                print('gdat.pericompprio')
                print(gdat.pericompprio)
                print('gdat.cosicompprio')
                print('gdat.rsmacompprio')
                print(gdat.rsmacompprio)
                gdat.duraprio = ephesos.retr_duratrantotl(gdat.pericompprio, gdat.rsmacompprio, gdat.cosicompprio)
                #gdat.deptprio = 1e3 * gdat.rratcompprio**2
            
            # check MAST
            if gdat.strgmast is None:
                if gdat.typetarg != 'inpt' and not gdat.booltargsynt:
                    gdat.strgmast = gdat.labltarg

            if gdat.typeverb > 0:
                print('gdat.strgmast')
                print(gdat.strgmast)
            
            if not gdat.boolforcoffl and gdat.strgmast is not None and not gdat.boolsrchmastdone:
                listdictticinear = astroquery.mast.Catalogs.query_object(gdat.strgmast, catalog='TIC', radius=gdat.strgradi)
                gdat.boolsrchmastdone = True
                if listdictticinear[0]['dstArcSec'] > 0.1:
                    if gdat.typeverb > 0:
                        print('The nearest source is more than 0.1 arcsec away from the target!')
                
                if gdat.typeverb > 0:
                    print('Found the target on MAST!')
                
                gdat.rascstar = listdictticinear[0]['ra']
                gdat.declstar = listdictticinear[0]['dec']
                gdat.stdvrascstar = 0.
                gdat.stdvdeclstar = 0.
                if gdat.radistar is None:
                    
                    if gdat.typeverb > 0:
                        print('Setting the stellar radius from the TIC.')
                    
                    gdat.radistar = listdictticinear[0]['rad']
                    gdat.stdvradistar = listdictticinear[0]['e_rad']
                    
                    if gdat.typeverb > 0:
                        if not np.isfinite(gdat.radistar):
                            print('Warning! TIC stellar radius is not finite.')
                        if not np.isfinite(gdat.radistar):
                            print('Warning! TIC stellar radius uncertainty is not finite.')
                if gdat.massstar is None:
                    
                    if gdat.typeverb > 0:
                        print('Setting the stellar mass from the TIC.')
                    
                    gdat.massstar = listdictticinear[0]['mass']
                    gdat.stdvmassstar = listdictticinear[0]['e_mass']
                    
                    if gdat.typeverb > 0:
                        if not np.isfinite(gdat.massstar):
                            print('Warning! TIC stellar mass is not finite.')
                        if not np.isfinite(gdat.stdvmassstar):
                            print('Warning! TIC stellar mass uncertainty is not finite.')
                if gdat.tmptstar is None:
                    
                    if gdat.typeverb > 0:
                        print('Setting the stellar temperature from the TIC.')
                    
                    gdat.tmptstar = listdictticinear[0]['Teff']
                    gdat.stdvtmptstar = listdictticinear[0]['e_Teff']
                    
                    if gdat.typeverb > 0:
                        if not np.isfinite(gdat.tmptstar):
                            print('Warning! TIC stellar temperature is not finite.')
                        if not np.isfinite(gdat.tmptstar):
                            print('Warning! TIC stellar temperature uncertainty is not finite.')
                gdat.jmagsyst = listdictticinear[0]['Jmag']
                gdat.hmagsyst = listdictticinear[0]['Hmag']
                gdat.kmagsyst = listdictticinear[0]['Kmag']
                gdat.vmagsyst = listdictticinear[0]['Vmag']
        
        # list of strings to be attached to file names for each energy bin
        gdat.liststrgener = [[] for p in gdat.indxinst[0]]
        
        if gdat.boolsimurflx:
            
            # type of baseline
            ## 'cons': constant
            ## 'step': step function
            gdat.true.typemodlblinshap = 'cons'

            for p in gdat.indxinst[0]:
                for e in range(gdat.numbener[p]):
                    gdat.liststrgener[p].append('ener%04d' % e)
            
            if gdat.true.typemodlblinshap == 'cons':
                for p in gdat.indxinst[0]:
                    if gdat.numbener[p] > 1 and gdat.true.typemodlblinener[p] == 'ener':
                        for e in range(gdat.numbener[p]):
                            tdpy.setp_para_defa(gdat, 'true', 'consblin%s' % gdat.liststrgener[p][e], np.array([0.]))
                    else:
                        tdpy.setp_para_defa(gdat, 'true', 'consblin', np.array([0.]))
                        
            elif gdat.true.typemodlblinshap == 'step':
                tdpy.setp_para_defa(gdat, 'true', 'consblinfrst', np.array([0.]))
                tdpy.setp_para_defa(gdat, 'true', 'consblinseco', np.array([0.]))
                tdpy.setp_para_defa(gdat, 'true', 'timestep', np.array([0.]))
                tdpy.setp_para_defa(gdat, 'true', 'scalstep', np.array([1.]))
            
            if gdat.true.boolmodlpsys or gdat.true.typemodl == 'cosc':
                tdpy.setp_para_defa(gdat, 'true', 'numbcomp', 1)

                gdat.true.indxcomp = np.arange(gdat.true.numbcomp)
                
                for namepara in ['epocmtra', 'peri', 'rsma', 'cosi']:
                    for j in gdat.true.indxcomp:
                        tdpy.setp_para_defa(gdat, 'true', namepara + 'com%d' % j, getattr(gdat, namepara + 'compprio')[j])

                if gdat.true.boolmodlpsys:
                    for j in gdat.true.indxcomp:
                        if gdat.numbener[p] > 1:
                            tdpy.setp_para_defa(gdat, 'true', 'rratcom0whit', 0.1)
                            for e in range(gdat.numbener[p]):
                                tdpy.setp_para_defa(gdat, 'true', 'rratcom%dener%04d' % (j, e), getattr(gdat, 'rratcompprio')[j])
                        else:
                            tdpy.setp_para_defa(gdat, 'true', 'rratcom%d' % j, getattr(gdat, 'rratcompprio')[j])
                        
                if gdat.true.typemodl == 'cosc':
                    tdpy.setp_para_defa(gdat, 'true', 'radistar', 1.)
                    tdpy.setp_para_defa(gdat, 'true', 'massstar', 1.)
                    tdpy.setp_para_defa(gdat, 'true', 'masscom0', 1.)
            
            if gdat.true.typemodl == 'supn':
                # temp
                minmtimesupn = np.amin(gdat.true.listtime[0][0][0]) + 0. * (np.amax(gdat.true.listtime[0][0][0]) - np.amin(gdat.true.listtime[0][0][0]))
                maxmtimesupn = np.amin(gdat.true.listtime[0][0][0]) + 1. * (np.amax(gdat.true.listtime[0][0][0]) - np.amin(gdat.true.listtime[0][0][0]))
                timesupn = tdpy.icdf_self(0.25, minmtimesupn, maxmtimesupn) - gdat.timeoffs
                tdpy.setp_para_defa(gdat, 'true', 'timesupn', timesupn)

                tdpy.setp_para_defa(gdat, 'true', 'coeflinesupn', 0.)

                tdpy.setp_para_defa(gdat, 'true', 'sigmgprobase', 2.) # [ppt]
                
                tdpy.setp_para_defa(gdat, 'true', 'rhoogprobase', 0.1) # [day]
                                
                tdpy.setp_para_defa(gdat, 'true', 'timebumpoffs', 0.5) # [day]
                                
                tdpy.setp_para_defa(gdat, 'true', 'amplbump', 10.) # [ppt]
                                
                tdpy.setp_para_defa(gdat, 'true', 'scalbump', 1.) # [day]
                                
                tdpy.setp_para_defa(gdat, 'true', 'coefquadsupn', 0.5) # [ppt]
                                
        # determine number of chunks
        gdat.numbchun = [np.zeros(gdat.numbinst[b], dtype=int) - 1 for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if gdat.boolsimurflx:
                    gdat.numbchun[b][p] = 1
                elif gdat.liststrgtypedata[b][p] == 'inpt':
                    gdat.numbchun[b][p] = len(gdat.listarrytser['raww'][b][p])
                elif b == 0 and (gdat.liststrginst[b][p] == 'TESS' or gdat.liststrginst[b][p].startswith('JWST')):
                    gdat.numbchun[b][p] = len(gdat.listarrylcurmast[p])
                    
                    #gdat.listarrytser['raww'][b][p] = gdat.listarrylcurmast[p]

                if gdat.booldiag:
                    if gdat.boolretrlcurmast:
                        for y in range(len(gdat.listarrylcurmast[p])):
                            if gdat.listarrylcurmast[p][y].ndim != 3:
                                print('')
                                print('')
                                print('')
                                print('gdat.listarrylcurmast[p][y]')
                                summgene(gdat.listarrylcurmast[p][y])
                                raise Exception('')
                    
                    if gdat.numbchun[b][p] <= 0:
                        print('')
                        print('')
                        print('')
                        print('bp')
                        print(b, p)
                        print('len(gdat.listarrylcurmast[p])')
                        print(len(gdat.listarrylcurmast[p]))
                        print('gdat.listarrylcurmast[p]')
                        print(gdat.listarrylcurmast[p])
                        for y in range(len(gdat.listarrylcurmast[p])):
                            print('gdat.listarrylcurmast[p][y]')
                            print(gdat.listarrylcurmast[p][y])
                        raise Exception('')

                    if gdat.numbchun[b][p] <= 0:
                        print('')
                        print('')
                        print('')
                        print('gdat.numbchun was not properly defined.')
                        print('gdat.numbchun')
                        print(gdat.numbchun)
                        print('gdat.numbchun[b][p]')
                        print(gdat.numbchun[b][p])
                        print('bp')
                        print(b, p)
                        print('(gdat.liststrginst[b][p] == TESS or gdat.liststrginst[b][p].startswith(JWST))')
                        print((gdat.liststrginst[b][p] == 'TESS' or gdat.liststrginst[b][p].startswith('JWST')))
                        print('gdat.boolsimurflx')
                        print(gdat.boolsimurflx)
                        print('gdat.typetarg')
                        print(gdat.typetarg)
                        print('gdat.liststrgtypedata')
                        print(gdat.liststrgtypedata)
                        print('gdat.liststrginst[b][p]')
                        print(gdat.liststrginst[b][p])
                        raise Exception('')
        
        gdat.indxchun = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if gdat.booldiag:
                    if gdat.numbchun[b][p] < 1:
                        print('gdat.numbchun[b][p]')
                        print(gdat.numbchun[b][p])
                        raise Exception('')
                gdat.indxchun[b][p] = np.arange(gdat.numbchun[b][p], dtype=int)
    
        ## type of inference over energy axis to perform inference using
        ### 'full': fit all energy bins simultaneously
        ### 'iter': iterate over energy bins
        tdpy.setp_para_defa(gdat, 'fitt', 'typemodlenerfitt', 'iter')
                    
        if gdat.typeverb > 0:
            print('gdat.fitt.typemodlenerfitt')
            print(gdat.fitt.typemodlenerfitt)
                        
            if gdat.boolretrlcurmast:
                for b in gdat.indxdatatser:
                    for p in gdat.indxinst[b]:
                        for y in gdat.indxchun[b][p]:
                            print('bpy')
                            print(b, p, y)
                            print('gdat.listarrylcurmast[p][y]')
                            summgene(gdat.listarrylcurmast[p][y])
                            print('gdat.listarrylcurmast[p][y][:, :, 0]')
                            summgene(gdat.listarrylcurmast[p][y][:, :, 0])
                            print('gdat.listarrylcurmast[p][y][:, :, 1]')
                            summgene(gdat.listarrylcurmast[p][y][:, :, 1])
                            print('gdat.listarrylcurmast[p][y][:, :, 2]')
                            summgene(gdat.listarrylcurmast[p][y][:, :, 2])
                            print('')

        if gdat.numbener[p] == 1:
            gdat.numbenermodl = 1
            gdat.numbeneriter = 1
            gdat.numbenerefes = 1
        elif gdat.fitt.typemodlenerfitt == 'full':
            gdat.numbenermodl = gdat.numbener[p]
            gdat.numbeneriter = 2
            gdat.numbenerefes = 2
        else:
            gdat.numbenermodl = 1
            gdat.numbeneriter = gdat.numbener[p] + 1
            gdat.numbenerefes = gdat.numbener[p] + 1
        gdat.indxdataiter = np.arange(gdat.numbeneriter)
        gdat.indxenermodl = np.arange(gdat.numbenermodl)

        #if gdat.listarrytser is None:
        gdat.listarrytser['raww'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        
        gdat.arrytser['bdtrlowr'] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtrlowr'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.arrytser['bdtrmedi'] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtrmedi'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.arrytser['bdtruppr'] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtruppr'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        
        gdat.arrytser['raww'] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.arrytser['maskcust'] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.arrytser['bdtr'] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.arrytser['bdtrbind'] = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        
        gdat.listarrytser['maskcust'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['temp'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['trnd'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtr'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listarrytser['bdtrbind'] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        
        # list of strings to be attached to file names for type of run over energy bins
        gdat.liststrgdataiter = [[] for r in gdat.indxdataiter]
        for e in gdat.indxdataiter:
            if e == 0:
                if gdat.numbener[p] > 1:
                    gdat.liststrgdataiter[0] = 'whit'
                else:
                    gdat.liststrgdataiter[0] = ''
            else:
                gdat.liststrgdataiter[e] = 'ener%04d' % (e - 1)
        
        if gdat.typeverb > 0:
            print('gdat.liststrgdataiter')
            print(gdat.liststrgdataiter)

        # load data
        ## data from MAST
        if gdat.boolretrlcurmast:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    gdat.listarrytser['raww'][b][p] = gdat.listarrylcurmast[p]
        
        ## user-input data
        if gdat.listpathdatainpt is not None:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        arry = np.loadtxt(gdat.listpathdatainpt[b][p][y], delimiter=',', skiprows=1)
                        gdat.listarrytser['raww'][b][p][y] = np.empty((arry.shape[0], arry.shape[1], 3))
                        gdat.listarrytser['raww'][b][p][y][:, :, 0:2] = arry[:, :, 0:2]
                        gdat.listarrytser['raww'][b][p][y][:, :, 2] = 1e-4 * arry[:, :, 1]
                        indx = np.argsort(gdat.listarrytser['raww'][b][p][y][:, 0])
                        gdat.listarrytser['raww'][b][p][y] = gdat.listarrytser['raww'][b][p][y][indx, :, :]
                        indx = np.where(gdat.listarrytser['raww'][b][p][y][:, 1] < 1e6)[0]
                        gdat.listarrytser['raww'][b][p][y] = gdat.listarrytser['raww'][b][p][y][indx, :, :]
                        gdat.listisec = None
        
        ## simulated data
        if gdat.boolsimurflx:

            gdat.true.listtime = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            gdat.true.time = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        if gdat.liststrginst[b][p] == 'TESS':
                            cade = 10. # [min]
                            delttime = cade / 60. / 24.
                            gdat.true.listtime[b][p][y] = 2459000. + np.concatenate([np.arange(0., 13.2, delttime), np.arange(14.2, 27.3, delttime)])
                        elif gdat.liststrginst[b][p] == 'JWST':
                            gdat.true.listtime[b][p][y] = 2459000. + np.arange(0.3, 0.7, 2. / 60. / 24.)
                        elif gdat.liststrginst[b][p].startswith('LSST'):
                            gdat.true.listtime[b][p][y] = 2459000. + np.random.rand(1000) * 10. * 365.
                        else:
                            raise Exception('')
                    gdat.true.time[b][p] = np.concatenate(gdat.true.listtime[b][p])
            
            gdat.time = gdat.true.time
            gdat.timeconc = [[] for b in gdat.indxdatatser]
            gdat.minmtimeconc = np.empty(gdat.numbdatatser)
            gdat.maxmtimeconc = np.empty(gdat.numbdatatser)
            for b in gdat.indxdatatser:
                if len(gdat.time[b]) > 0:
                    gdat.timeconc[b] = np.concatenate(gdat.time[b])
                    gdat.minmtimeconc[b] = np.amin(gdat.timeconc[b])
                    gdat.maxmtimeconc[b] = np.amax(gdat.timeconc[b])
            
            if gdat.true.typemodl == 'flar':
                tdpy.setp_para_defa(gdat, 'true', 'numbflar', 1)
                gdat.true.indxflar = np.arange(gdat.true.numbflar)
                for k in gdat.true.indxflar:
                    tdpy.setp_para_defa(gdat, 'true', 'amplflar%04d' % k, 0.1)
                    timeflar = tdpy.icdf_self(np.random.rand(), gdat.minmtimeconc[0], gdat.minmtimeconc[0]) 
                    tdpy.setp_para_defa(gdat, 'true', 'timeflar%04d' % k, timeflar)
                    tdpy.setp_para_defa(gdat, 'true', 'tsclflar%04d' % k, 1.)
                    
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        gdat.listarrytser['raww'][b][p][y] = np.empty((gdat.true.listtime[b][p][y].size, gdat.numbener[p], 3))
                        gdat.listarrytser['raww'][b][p][y][:, :, 0] = gdat.true.listtime[b][p][y][:, None]
            
        if gdat.timeoffs is None:
            timeoffs = 0.
            cntr = 0
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    print('gdat.indxchun')
                    print(gdat.indxchun)
                    for y in gdat.indxchun[b][p]:
                        timeoffs += np.sum(gdat.listarrytser['raww'][b][p][y][:, 0, 0])
                        cntr += gdat.listarrytser['raww'][b][p][y].shape[0]
            timeoffs /= cntr
            gdat.timeoffs = int(timeoffs / 1000.) * 1000.
        
        if gdat.fitt.typemodlenerfitt == 'iter':
            if gdat.typeinfe == 'samp':
                gdat.fitt.listdictsamp = []
            else:
                gdat.fitt.listdictmlik = []

        if gdat.boolsimurflx:
        
            init_modl(gdat, 'true')

            setp_modlbase(gdat, 'true')
            
            #gdat.true.typemodlenerfitt = 'full'
            
            if gdat.numbener[p] == 1:
                gdat.numbenermodl = gdat.numbener[p]
                gdat.numbeneriter = 1
            else:
                gdat.numbenermodl = 1
                gdat.numbeneriter = gdat.numbener[p]

            if gdat.true.boolmodlcomp:
                for j in range(gdat.epocmtracompprio.size):
                    for name in gdat.true.listnameparacomp[j]:
                        setattr(gdat.true, '%scom%d' % (name, j), getattr(gdat, '%scompprio' % name)[j])
            
            dictparainpt = dict()
            for name in gdat.true.listnameparafull:
                dictparainpt[name] = getattr(gdat.true, name)
            
            if gdat.booldiag:
                if len(dictparainpt) == 0:
                    raise Exception('')
            gdat.true.dictmodl = retr_dictmodl_mile(gdat, gdat.true.time, dictparainpt, 'true')[0]
            
            if gdat.true.typemodlblinshap == 'gpro':
                dictrflx = retr_rflxmodl_mile_gpro(gdat, 'true', gdat.true.time, dictparainpt)
                gdat.true.dictrflxmodl['blin'] = dictrflx['blin']

            # generate flux data
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        
                        # noise per cadence
                        gdat.listarrytser['raww'][b][p][y][:, :, 2] = 1e-2
                        gdat.listarrytser['raww'][b][p][y][:, :, 1] = gdat.true.dictmodl['totl'][0][p][y]
                        
                        gdat.listarrytser['raww'][b][p][y][:, :, 1] += \
                                 np.random.randn(gdat.true.listtime[b][p][y].size * gdat.numbener[p]).reshape((gdat.true.listtime[b][p][y].size, gdat.numbener[p])) * \
                                                                                                                            gdat.listarrytser['raww'][b][p][y][:, :, 2]
        else:
            for p in gdat.indxinst[0]:
                # define number of energy bins if any photometric data exist
                gdat.numbener[p] = gdat.listarrytser['raww'][0][p][0].shape[1]
                for e in range(gdat.numbener[p]):
                    if e == 0 and gdat.numbener[p] == 1:
                        gdat.liststrgener[p].append('')
                    else:
                        gdat.liststrgener[p].append('ener%04d' % e)

        # make white light curve
        if gdat.numbener[p] > 1:
            
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        arrywhit = np.empty((gdat.listarrytser['raww'][b][p][y].shape[0], 3))
                        arrywhit[:, 0] = gdat.listarrytser['raww'][b][p][y][:, 0, 0]
                        arrywhit[:, 1] = np.mean(gdat.listarrytser['raww'][b][p][y][:, :, 1], 1)
                        arrywhit[:, 2] = np.sqrt(np.sum(gdat.listarrytser['raww'][b][p][y][:, :, 2]**2, 1)) / gdat.numbener[p]
                        arrytemp = np.empty((gdat.listarrytser['raww'][b][p][y].shape[0], gdat.numbener[p] + 1, 3))
                        arrytemp[:, 0, :] = arrywhit
                        arrytemp[:, 1:, :] = gdat.listarrytser['raww'][b][p][y]
                        gdat.listarrytser['raww'][b][p][y] = arrytemp
        
        if gdat.typeverb > 1:
            print('gdat.numbener[p]')
            print(gdat.numbener[p])
            
        gdat.indxener = [[] for p in gdat.indxinst[0]]
        for p in gdat.indxinst[0]:
            gdat.indxener[p] = np.arange(gdat.numbener[p])
            
        if gdat.numbener[p] > 1 and gdat.typeverb > 0:
            print('gdat.fitt.typemodlenerfitt')
            print(gdat.fitt.typemodlenerfitt)

        # concatenate data across sectors
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                #if gdat.liststrgtypedata[b][p] == 'inpt' and gdat.liststrgtypedata[b][p].startswith('simu'):
                gdat.arrytser['raww'][b][p] = np.concatenate(gdat.listarrytser['raww'][b][p])
        
        if gdat.booldiag:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        if len(gdat.listarrytser['raww'][b][p][y]) == 0:
                            print('')
                            print('')
                            print('')
                            print('len(gdat.listarrytser[raww][b][p][y]) == 0')
                            print('bpy')
                            print('%d, %d, %d' % (b, p, y))
                            print('gdat.listarrytser[raww][b][p][y]')
                            summgene(gdat.listarrytser['raww'][b][p][y])
                            raise Exception('')

                    if gdat.liststrginst[b][p] == 'TESS' and not hasattr(gdat, 'listtsec') and (gdat.liststrgtypedata[b][p] != 'simutargsynt'):
                        print('')
                        print('')
                        print('')
                        print('listtsec is not defined while accessing TESS data of particular target.')
                        print('b, p')
                        print(b, p)
                        print('gdat.liststrgtypedata')
                        print(gdat.liststrgtypedata)
                        print('gdat.boolretrlcurmast')
                        print(gdat.boolretrlcurmast)
                        raise Exception('')
                    
                    if gdat.liststrginst[b][p] == 'TESS' and gdat.listtsec is None:
                        print('')
                        print('')
                        print('')
                        print('Instrument is TESS, but list of sectors is None.')
                        print('gdat.listtsec')
                        print(gdat.listtsec)
                        print('gdat.liststrginst')
                        print(gdat.liststrginst)
                        raise Exception('')
                        
        if gdat.liststrgchun is None:
            gdat.listlablchun = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            gdat.liststrgchun = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        
                        if gdat.liststrginst[b][p] == 'TESS' and gdat.listtsec is not None:
                            
                            if gdat.booldiag:
                                if gdat.numbchun[b][p] != len(gdat.listtsec):
                                    print('')
                                    print('')
                                    print('')
                                    print('')
                                    print('bpy')
                                    print('gdat.numbchun[b][p] != len(gdat.listtsec)')
                                    print(b, p, y)
                                    print('gdat.listtsec')
                                    print(gdat.listtsec)
                                    print('gdat.indxchun')
                                    print(gdat.indxchun)
                                    print('gdat.numbchun')
                                    print(gdat.numbchun)
                                    raise Exception('')

                            gdat.listlablchun[b][p][y] = 'Sectors %d' % gdat.listtsec[y]
                            gdat.liststrgchun[b][p][y] = 'sc%02d' % gdat.listtsec[y]
                        else:
                            gdat.liststrgchun[b][p][y] = 'ch%02d' % y

        # check the user-defined gdat.listpathdatainpt
        if gdat.listpathdatainpt is not None:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if not isinstance(gdat.listpathdatainpt[b][p], list):
                        raise Exception('')
        
        if gdat.boolnormphot:
            gdat.labltserphot = 'Relative flux'
        else:
            gdat.labltserphot = 'ADC Counts [e$^-$/s]'
        gdat.listlabltser = [gdat.labltserphot, 'Radial Velocity [km/s]']
        gdat.liststrgtser = ['rflx', 'rvel']
        gdat.liststrgtsercsvv = ['flux', 'rv']
        
        if gdat.offstextatmoraditmpt is None:
            gdat.offstextatmoraditmpt = [[0.3, -0.5], [0.3, -0.5], [0.3, -0.5], [0.3, 0.5]]
        if gdat.offstextatmoradimetr is None:
            gdat.offstextatmoradimetr = [[0.3, -0.5], [0.3, -0.5], [0.3, -0.5], [0.3, 0.5]]
    
    if gdat.typetarg == 'inpt':
        if gdat.vmagsyst is None:
            gdat.vmagsyst = 0.
        if gdat.jmagsyst is None:
            gdat.jmagsyst = 0.
        if gdat.hmagsyst is None:
            gdat.hmagsyst = 0.
        if gdat.kmagsyst is None:
            gdat.kmagsyst = 0.

    if gdat.booltserdata:
        # check availability of data 
        booldataaval = False
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                for y in gdat.indxchun[b][p]:
                    if len(gdat.listarrytser['raww'][b][p][y]) == 0:
                        print('bpy')
                        print(b, p, y)
                        print('gdat.indxchun')
                        print(gdat.indxchun)
                        raise Exception('')
                    if len(gdat.listarrytser['raww'][b][p][y]) > 0:
                        booldataaval = True
        if not booldataaval:
            if gdat.typeverb > 0:
                print('No data found. Returning...')
            return gdat.dictmileoutp
    
        # plot raw data
        for strgmodl in gdat.liststrgmodl:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        if gdat.boolplottser:
                            plot_tser(gdat, strgmodl, b, p, y, 'raww')
                    if gdat.boolplottser:
                        gdat.arrytser['raww'][b][p] = np.concatenate(gdat.listarrytser['raww'][b][p], axis=0)
        
        if gdat.booldiag:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        if len(gdat.listarrytser['raww'][b][p][y]) == 0:
                            print('bpy')
                            print(b, p, y)
                            raise Exception('')
            
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if not np.isfinite(gdat.arrytser['raww'][b][p]).all():
                        print('b, p')
                        print(b, p)
                        indxbadd = np.where(~np.isfinite(gdat.arrytser['raww'][b][p]))[0]
                        print('gdat.arrytser[raww][b][p]')
                        summgene(gdat.arrytser['raww'][b][p])
                        print('indxbadd')
                        summgene(indxbadd)
                        raise Exception('')
        
        # obtain 'maskcust' (obtained after custom mask, if any) time-series bundle after applying user-defined custom mask, if any
        if gdat.listlimttimemask is not None:
            
            if gdat.typeverb > 0:
                print('Masking the data...')
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    numbmask = len(gdat.listlimttimemask[b][p])
                    for y in gdat.indxchun[b][p]:
                        listindxtimemask = []
                        for k in range(numbmask):
                            indxtimemask = np.where((gdat.listarrytser['raww'][b][p][y][:, 0] < gdat.listlimttimemask[b][p][k][1]) & \
                                                    (gdat.listarrytser['raww'][b][p][y][:, 0] > gdat.listlimttimemask[b][p][k][0]))[0]
                            listindxtimemask.append(indxtimemask)
                        listindxtimemask = np.concatenate(listindxtimemask)
                        listindxtimegood = np.setdiff1d(np.arange(gdat.listarrytser['raww'][b][p][y].shape[0]), listindxtimemask)
                        gdat.listarrytser['maskcust'][b][p][y] = gdat.listarrytser['raww'][b][p][y][listindxtimegood, :]
                        if gdat.boolplottser:
                            plot_tser(gdat, strgmodl, b, p, y, 'maskcust')
                    gdat.arrytser['maskcust'][b][p] = np.concatenate(gdat.listarrytser['maskcust'][b][p], 0)
                    if gdat.boolplottser:
                        plot_tser(gdat, strgmodl, b, p, y, 'maskcust')
        else:
            gdat.arrytser['maskcust'] = gdat.arrytser['raww']
            gdat.listarrytser['maskcust'] = gdat.listarrytser['raww']
        
        gdat.boolmodltran = gdat.boolinfe and gdat.fitt.boolmodltran or gdat.boolsimurflx and gdat.true.boolmodltran

        # detrending
        ## determine whether to use any mask for detrending
        if gdat.boolinfe and gdat.fitt.boolmodltran and gdat.duraprio is not None and len(gdat.duraprio) > 0:
            # assign the prior orbital solution to the baseline-detrend mask
            gdat.epocmask = gdat.epocmtracompprio
            gdat.perimask = gdat.pericompprio
            gdat.duramask = 2. * gdat.duraprio
        else:
            gdat.epocmask = None
            gdat.perimask = None
            gdat.duramask = None
                            
        # obtain bdtrnotr time-series bundle, the baseline-detrended light curve with no masking due to identified transiting object
        if gdat.numbinst[0] > 0 and gdat.boolbdtranyy:
            gdat.listobjtspln = [[[[] for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]] for b in gdat.indxdatatser]
            gdat.indxsplnregi = [[[[] for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]] for b in gdat.indxdatatser]
            gdat.listindxtimeregi = [[[[] for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]] for b in gdat.indxdatatser]
            gdat.indxtimeregioutt = [[[[] for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]] for b in gdat.indxdatatser]
            
            gdat.numbiterbdtr = [[0 for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]]
            numbtimecutt = [[1 for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]]
            
            print('Listing all strings of detrending variables...')
            for z, timescalbdtrspln in enumerate(gdat.listtimescalbdtrspln):
                for wr in range(gdat.maxmnumbiterbdtr):
                    strgarrybdtrinpt, strgarryclipoutp, strgarrybdtroutp, strgarryclipinpt, strgarrybdtrblin = retr_namebdtrclip(z, wr)
                    gdat.listarrytser[strgarrybdtrinpt] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
                    gdat.listarrytser[strgarryclipoutp] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
                    gdat.listarrytser[strgarrybdtroutp] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
                    gdat.listarrytser[strgarryclipinpt] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
                    gdat.listarrytser[strgarrybdtrblin] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            
            # iterate over all detrending time scales (including, but not limited to the (first) time scale used for later analysis and model)
            gdat.indxenerclip = 0
            for z, timescalbdtrspln in enumerate(gdat.listtimescalbdtrspln):
                
                if timescalbdtrspln == 0:
                    continue
                
                strgarrybdtr = 'bdtrts%02d' % z
                gdat.listarrytser[strgarrybdtr] = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
                
                # baseline-detrending
                b = 0
                for p in gdat.indxinst[0]:
                    if gdat.typeverb > 0:
                        if gdat.boolbdtr[0][p]:
                            print('Will detrend the photometric time-series before estimating the priors...')
                        else:
                            print('Will NOT detrend the photometric time-series before estimating the priors...')
                    if not gdat.boolbdtr[0][p]:
                        continue

                    for y in gdat.indxchun[0][p]:
                        
                        gdat.listtimebrek = None

                        if gdat.typeverb > 0:
                            print('Detrending data from chunk %s...' % gdat.liststrgchun[0][p][y])
                        
                        indxtimetotl = np.arange(gdat.listarrytser['maskcust'][0][p][y].shape[0])
                        indxtimekeep = np.copy(indxtimetotl)
                        
                        r = 0
                        while True:
                            
                            if gdat.typeverb > 0:
                                print('Iteration %d' % r)
                            
                            # construct the variable names for this time scale and trial
                            strgarrybdtrinpt, strgarryclipoutp, strgarrybdtroutp, strgarryclipinpt, strgarrybdtrblin = retr_namebdtrclip(z, r)
                            
                            # perform trial mask
                            if gdat.typeverb > 0:
                                print('Trial filtering with %.3g percent of the data points...' % \
                                                            (100. * indxtimekeep.size / gdat.listarrytser['maskcust'][0][p][y].shape[0]))
                            gdat.listarrytser[strgarrybdtrinpt][0][p][y] = gdat.listarrytser['maskcust'][0][p][y][indxtimekeep, :, :]
                            
                            if gdat.booldiag and indxtimekeep.size < 2:
                                raise Exception('')

                            if gdat.boolplottser:
                                plot_tser(gdat, strgmodl, 0, p, y, strgarrybdtrinpt, booltoge=False)
                            
                            # perform trial detrending
                            if gdat.typeverb > 0:
                                print('Trial detrending into %s...' % strgarryclipinpt)
                            bdtr_wrap(gdat, 0, p, y, gdat.epocmask, gdat.perimask, gdat.duramask, strgarrybdtrinpt, strgarryclipinpt, 'temp', \
                                                                                                                timescalbdtrspln=timescalbdtrspln)
                            
                            if r == 0:
                                gdat.listtimebrekfrst = np.copy(gdat.listtimebrek)
                                gdat.numbregibdtr = len(gdat.rflxbdtrregi)
                                gdat.indxregibdtr = np.arange(gdat.numbregibdtr)
                                gdat.indxtimeregiouttfrst = [[] for gg in gdat.indxregibdtr]
                                for kk in gdat.indxregibdtr:
                                    gdat.indxtimeregiouttfrst[kk] = np.copy(gdat.indxtimeregioutt[b][p][y][kk])
                            else:
                                if len(gdat.listtimebrek) != len(gdat.listtimebrekfrst):
                                    print('gdat.listtimebrek')
                                    print(gdat.listtimebrek)
                                    print('gdat.listtimebrekfrst')
                                    print(gdat.listtimebrekfrst)
                                    print('Number of edges changed.')
                                    raise Exception('')
                                elif gdat.boolbrekregi and ((gdat.listtimebrek[:-1] - gdat.listtimebrekfrst[:-1]) != 0.).any():
                                    print('Edges moved.')
                                    print('gdat.listtimebrek')
                                    print(gdat.listtimebrek)
                                    print('gdat.listtimebrekfrst')
                                    print(gdat.listtimebrekfrst)
                                    raise Exception('')

                            if gdat.boolplottser:
                                plot_tser_bdtr(gdat, b, p, y, z, r, strgarrybdtrinpt, strgarryclipinpt)
            
                                plot_tser(gdat, strgmodl, 0, p, y, strgarryclipinpt, booltoge=False)
                    
                            if gdat.typeverb > 0:
                                print('Determining outlier limits...')
                            
                            # sigma-clipping
                            lcurclip, lcurcliplowr, lcurclipuppr = scipy.stats.sigmaclip(gdat.listarrytser[strgarryclipinpt][0][p][y][:, :, 1], low=3., high=3.)
                            
                            indxtimeclipkeep = np.where((gdat.listarrytser[strgarryclipinpt][0][p][y][:, gdat.indxenerclip, 1] < lcurclipuppr) & \
                                                        (gdat.listarrytser[strgarryclipinpt][0][p][y][:, gdat.indxenerclip, 1] > lcurcliplowr))[0]
                            
                            if indxtimeclipkeep.size < 2:
                                print('No time samples left after clipping...')
                                print('gdat.listarrytser[strgarryclipinpt][0][p][y][:, gdat.indxenerclip, 1]')
                                summgene(gdat.listarrytser[strgarryclipinpt][0][p][y][:, gdat.indxenerclip, 1])
                                print('lcurcliplowr')
                                print(lcurcliplowr)
                                print('lcurclipuppr')
                                print(lcurclipuppr)
                                raise Exception('')
                            
                            #indxtimeclipmask = np.setdiff1d(np.arange(gdat.listarrytser[strgarryclipinpt][0][p][y][:, gdat.indxenerclip, 1].size), indxtimeclipkeep)
                            
                            # cluster indices of masked times
                            #listindxtimemaskclus = []
                            #for k in range(len(indxtimemask)):
                            #    if k == 0 or indxtimemask[k] != indxtimemask[k-1] + 1:
                            #        listindxtimemaskclus.append([indxtimemask[k]])
                            #    else:
                            #        listindxtimemaskclus[-1].append(indxtimemask[k])
                            #print('listindxtimemaskclus')
                            #print(listindxtimemaskclus)
                            
                            #print('Filtering clip times with index indxtimekeep into %s...' % strgarryclipoutp)
                            #gdat.listarrytser[strgarryclipoutp][0][p][y] = gdat.listarrytser['maskcust'][0][p][y][indxtimekeep, :]
                            
                            #print('Thinning the mask...')
                            #indxtimeclipmask = np.random.choice(indxtimeclipmask, size=int(indxtimeclipmask.size*0.7), replace=False)
                            
                            #print('indxtimeclipmask')
                            #summgene(indxtimeclipmask)

                            #indxtimeclipkeep = np.setdiff1d(np.arange(gdat.listarrytser[strgarryclipinpt][0][p][y][:, 1].size), indxtimeclipmask)
                            
                            indxtimekeep = indxtimekeep[indxtimeclipkeep]
                            
                            if gdat.booldiag and indxtimekeep.size < 2:
                                print('indxtimekeep')
                                print(indxtimekeep)
                                raise Exception('')

                            #boolexit = True
                            #for k in range(len(listindxtimemaskclus)):
                            #    # decrease mask

                            #    # trial detrending
                            #    bdtr_wrap(gdat, 0, p, y, gdat.epocmask, gdat.perimask, gdat.duramask, strgarrybdtrinpt, strgarryclipinpt, 'temp', timescalbdtrspln=timescalbdtrspln)
                            #    
                            #    chi2 = np.sum((gdat.listarrytser[strgarryclipinpt][0][p][y][:, 1] - gdat.listarrytser[strgarryclipinpt][0][p][y][:, 1])**2 / 
                            #                                                   gdat.listarrytser[strgarryclipinpt][0][p][y][:, 2]**2) / gdat.listarrytser[strgarryclipinpt][0][p][y][:, 1].size
                            #    if chi2 > 1.1:
                            #        boolexit = False
                            #
                            #    if gdat.boolplottser:
                            #        plot_tser(gdat, strgmodl, 0, p, y, strgarryclipoutp, booltoge=False)
                            
                            #if gdat.boolplottser:
                            #    plot_tser(gdat, strgmodl, 0, p, y, strgarrybdtroutp, booltoge=False)
                            

                            if r == gdat.maxmnumbiterbdtr - 1 or gdat.listarrytser[strgarryclipinpt][0][p][y][:, gdat.indxenerclip, 1].size == indxtimeclipkeep.size:
                                rflxtren = []
                                for kk in gdat.indxregibdtr:
                                    if gdat.typebdtr == 'gpro':
                                        rflxtren.append(gdat.listobjtspln[b][p][y][kk].predict( \
                                                                     gdat.listarrytser['maskcust'][b][p][y][gdat.indxtimeregioutt[b][p][y][kk], gdat.indxenerclip, 1], \
                                                                          t=gdat.listarrytser['maskcust'][b][p][y][:, gdat.indxenerclip, 0], \
                                                                                                                                 return_cov=False, return_var=False))
                                        
                                        #print('gdat.listindxtimeregi[b][p][y][kk]')
                                        #summgene(gdat.listindxtimeregi[b][p][y][kk])
                                        #print('gdat.indxtimeregioutt[b][p][y][kk]')
                                        #summgene(gdat.indxtimeregioutt[b][p][y][kk])
                                    
                                    if gdat.typebdtr == 'spln':
                                        rflxtren.append(gdat.listobjtspln[b][p][y][kk](gdat.listarrytser['maskcust'][b][p][y][:, gdat.indxenerclip, 0]))
                                gdat.listarrytser['bdtr'][0][p][y] = np.copy(gdat.listarrytser['maskcust'][0][p][y])
                                
                                #print('gdat.listarrytser[maskcust][0][p][y][:, gdat.indxenerclip, 1]')
                                #summgene(gdat.listarrytser['maskcust'][0][p][y][:, gdat.indxenerclip, 1])
                                #print('gdat.listarrytser[bdtr][0][p][y][:, gdat.indxenerclip, 1]')
                                #summgene(gdat.listarrytser['bdtr'][0][p][y][:, gdat.indxenerclip, 1])
                                #print('np.concatenate(rflxtren)')
                                #summgene(np.concatenate(rflxtren))
                                
                                gdat.listarrytser['bdtr'][0][p][y][:, gdat.indxenerclip, 1] = \
                                                1. + gdat.listarrytser['maskcust'][0][p][y][:, gdat.indxenerclip, 1] - np.concatenate(rflxtren)
                            
                                if r == gdat.maxmnumbiterbdtr - 1:
                                    print('Maximum number of trial detrending iterations attained. Breaking the loop...')
                                if gdat.listarrytser[strgarryclipinpt][0][p][y][:, gdat.indxenerclip, 1].size == indxtimeclipkeep.size:
                                    print('No more clipping is needed. Breaking the loop...')
                                if gdat.typeverb > 0:
                                    print('')
                                    print('')
                                
                                break
                                
                            else:
                                # plot the trial detrended and sigma-clipped time-series data
                                #print('strgarrybdtroutp')
                                #print(strgarrybdtroutp)
                                #if gdat.boolplottser:
                                #    plot_tser(gdat, strgmodl, 0, p, y, strgarryclipoutp, booltoge=False)
                                r += 1
                            
                                if gdat.typeverb > 0:
                                    print('')
                                    print('')

                        #gdat.numbiterbdtr[p][y] = r
                        #bdtr_wrap(gdat, 0, p, y, gdat.epocmask, gdat.perimask, gdat.duramask, strgarryclipoutp, strgarrybdtroutp, strgarrybdtrblin, timescalbdtrspln=timescalbdtrspln)
                        
                        #gdat.listarrytser[strgarrybdtr][0][p][y] = gdat.listarrytser[strgarrybdtroutp][0][p][y]
            
            if gdat.listtimescalbdtrspln[0] == 0.:
                gdat.listarrytser['bdtr'] = gdat.listarrytser['maskcust']

            # merge chunks
            for p in gdat.indxinst[0]:
                gdat.arrytser['bdtr'][0][p] = np.concatenate(gdat.listarrytser['bdtr'][0][p], 0)
            
            # write baseline-detrended light curve
            for p in gdat.indxinst[0]:
                
                if not gdat.boolbdtr[0][p]:
                    continue

                for e in gdat.indxener[p]:

                    if gdat.numbchun[0][p] > 1:
                        path = gdat.pathdatatarg + 'arrytserbdtr%s%s.csv' % (gdat.liststrginst[0][p], gdat.liststrgener[p][e])
                        if not os.path.exists(path):
                            if gdat.typeverb > 0:
                                print('Writing to %s...' % path)
                            np.savetxt(path, gdat.arrytser['bdtr'][0][p][:, e, :], delimiter=',', \
                                                            header='time,%s,%s_err' % (gdat.liststrgtsercsvv[0], gdat.liststrgtsercsvv[0]))
                    
                    for y in gdat.indxchun[0][p]:
                        path = gdat.pathdatatarg + 'arrytserbdtr%s%s%s.csv' % (gdat.liststrginst[0][p], gdat.liststrgchun[0][p][y], gdat.liststrgener[p][e])
                        if not os.path.exists(path):
                            if gdat.typeverb > 0:
                                print('Writing to %s...' % path)
                            np.savetxt(path, gdat.listarrytser['bdtr'][0][p][y][:, e, :], delimiter=',', \
                                                           header='time,%s,%s_err' % (gdat.liststrgtsercsvv[0], gdat.liststrgtsercsvv[0]))
        
            if gdat.boolplottser:
                for p in gdat.indxinst[0]:
                    if gdat.boolbdtr[0][p]:
                        for y in gdat.indxchun[0][p]:
                            plot_tser(gdat, strgmodl, 0, p, y, 'bdtr')
                        plot_tser(gdat, strgmodl, 0, p, None, 'bdtr')
        
        else:
            gdat.arrytser['bdtr'] = gdat.arrytser['maskcust']
            gdat.listarrytser['bdtr'] = gdat.listarrytser['maskcust']
        
        if gdat.booldiag:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if len(gdat.arrytser['bdtr'][b][p]) == 0:
                        raise Exception('')

        # update the time axis
        gdat.listtime = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.listtimefine = [[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.timeconc = [[] for b in gdat.indxdatatser]
        gdat.timefineconc = [[] for b in gdat.indxdatatser]
        gdat.time = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.timefine = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                gdat.time[b][p] = gdat.arrytser['bdtr'][b][p][:, 0, 0]
                for y in gdat.indxchun[b][p]:
                    gdat.listtime[b][p][y] = gdat.listarrytser['bdtr'][b][p][y][:, 0, 0]
                    difftimefine = 0.5 * np.amin(gdat.listtime[b][p][y][1:] - gdat.listtime[b][p][y][:-1])
                    gdat.listtimefine[b][p][y] = np.arange(np.amin(gdat.listtime[b][p][y]), np.amax(gdat.listtime[b][p][y]) + difftimefine, difftimefine)
                gdat.timefine[b][p] = np.concatenate(gdat.listtimefine[b][p])
            if len(gdat.time[b]) > 0:
                gdat.timeconc[b] = np.concatenate(gdat.time[b])
                gdat.timefineconc[b] = np.concatenate(gdat.timefine[b])

        # sampling rate (cadence)
        ## temporal
        gdat.cadetime = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                gdat.cadetime[b][p] = np.amin(gdat.timeconc[0][1:] - gdat.timeconc[0][:-1])
        if gdat.numbener[p] > 1:
            gdat.ratesampener = np.amin(gdat.listener[p][1:] - gdat.listener[p][:-1])
        
        if gdat.boolsrchflar:
            # size of the window for the flare search
            gdat.sizewndwflar = np.empty(gdat.numbinst[0], dtype=int)
            for p in gdat.indxinst[0]:
                gdat.sizewndwflar[p] = int((1. / 24.) / gdat.cadetime[0][p])
        
        # rebinning
        gdat.numbrebn = 50
        gdat.indxrebn = np.arange(gdat.numbrebn)
        gdat.listdeltrebn = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                gdat.minmdeltrebn = max(100. * gdat.cadetime[b][p], 0.1 * 0.3 * (gdat.timeconc[0][-1] - gdat.timeconc[0][0]))
                gdat.maxmdeltrebn =  0.3 * (gdat.timeconc[0][-1] - gdat.timeconc[0][0])
                gdat.listdeltrebn[b][p] = np.linspace(gdat.minmdeltrebn, gdat.maxmdeltrebn, gdat.numbrebn)
        
        # search for periodic boxes
        if gdat.boolsrchpbox:
            
            # temp
            for p in gdat.indxinst[0]:
                
                # input data to the periodic box search pipeline
                arry = np.copy(gdat.arrytser['bdtr'][0][p][:, 0, :])
                
                if gdat.dictpboxinpt is None:
                    gdat.dictpboxinpt = dict()
                
                if not 'typeverb' in gdat.dictpboxinpt:
                    gdat.dictpboxinpt['typeverb'] = gdat.typeverb
                
                if not 'pathvisu' in gdat.dictpboxinpt:
                    if gdat.boolplot:
                        gdat.dictpboxinpt['pathvisu'] = gdat.pathvisutarg
                
                if not 'boolsrchposi' in gdat.dictpboxinpt:
                    if 'cosc' in gdat.listtypeanls:
                        gdat.dictpboxinpt['boolsrchposi'] = True
                    else:
                        gdat.dictpboxinpt['boolsrchposi'] = False
                gdat.dictpboxinpt['pathdata'] = gdat.pathdatatarg
                gdat.dictpboxinpt['timeoffs'] = gdat.timeoffs
                gdat.dictpboxinpt['strgextn'] = '%s_%s' % (gdat.liststrginst[0][p], gdat.strgtarg)
                gdat.dictpboxinpt['typefileplot'] = gdat.typefileplot
                gdat.dictpboxinpt['figrsizeydobskin'] = gdat.figrsizeydobskin
                gdat.dictpboxinpt['alphraww'] = gdat.alphraww

                dictpboxoutp = ephesos.srch_pbox(arry, **gdat.dictpboxinpt)
                
                gdat.dictmileoutp['dictpboxoutp'] = dictpboxoutp
                
                if gdat.epocmtracompprio is None:
                    gdat.epocmtracompprio = dictpboxoutp['epocmtracomp']
                if gdat.pericompprio is None:
                    gdat.pericompprio = dictpboxoutp['pericomp']
                gdat.deptprio = 1. - 1e-3 * dictpboxoutp['depttrancomp']
                gdat.duraprio = dictpboxoutp['duracomp']
                gdat.cosicompprio = np.zeros_like(dictpboxoutp['epocmtracomp']) 
                gdat.rratcompprio = np.sqrt(1e-3 * gdat.deptprio)
                gdat.rsmacompprio = np.sin(np.pi * gdat.duraprio / gdat.pericompprio / 24.)
                
                gdat.perimask = gdat.pericompprio
                gdat.epocmask = gdat.epocmtracompprio
                gdat.duramask = 2. * gdat.duraprio
        
        if gdat.typeverb > 0:
            print('gdat.epocmask')
            print(gdat.epocmask)
            print('gdat.perimask')
            print(gdat.perimask)
            print('gdat.duramask')
            print(gdat.duramask)
        
        # search for flares
        if gdat.boolsrchflar:
            dictsrchflarinpt['pathvisu'] = gdat.pathvisutarg
            
            gdat.listindxtimeflar = [[[] for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]]
            gdat.listmdetflar = [[[] for y in gdat.indxchun[0][p]] for p in gdat.indxinst[0]]
            gdat.precphot = [np.empty(gdat.numbchun[0][p]) for p in gdat.indxinst[0]]
            gdat.thrsrflxflar = [np.empty(gdat.numbchun[0][p]) for p in gdat.indxinst[0]]
            
            for p in gdat.indxinst[0]:
                for y in gdat.indxchun[0][p]:
                    gdat.listarrytser['bdtrmedi'][0][p][y] = np.empty_like(gdat.listarrytser['bdtr'][0][p][y])
                    gdat.listarrytser['bdtrlowr'][0][p][y] = np.empty_like(gdat.listarrytser['bdtr'][0][p][y])
                    gdat.listarrytser['bdtruppr'][0][p][y] = np.empty_like(gdat.listarrytser['bdtr'][0][p][y])

                    if gdat.typemodlflar == 'outl':
                        listydat = gdat.listarrytser['bdtr'][0][p][y][:, 0, 1]
                        numbtime = listydat.size
                        tsermedi = np.empty(numbtime)
                        tseruppr = np.empty(numbtime)
                        for t in range(listydat.size):
                            # time-series of the median inside a window
                            minmindxtimewind = max(0, t - gdat.sizewndwflar)
                            maxmindxtimewind = min(numbtime - 1, t + gdat.sizewndwflar)
                            indxtimewind = np.arange(minmindxtimewind, maxmindxtimewind + 1)
                            medi, lowr, uppr = np.percentile(listydat[indxtimewind], [5., 50., 95.])
                            gdat.listarrytser['bdtrmedi'][0][p][y][t, 0, 1] = medi
                            
                            # time-series of the decision boundary
                            indxcent = np.where((listydat > np.percentile(listydat, 1.)) & (listydat < np.percentile(listydat, 99.)))[0]
                            
                            # standard deviation inside the window without the outliers
                            stdv = np.std(listydat[indxcent])
                            
                            gdat.precphot[p][y] = stdv
                            listmdetflar = (listydat - medi) / stdv
                            gdat.thrsrflxflar[p][y] = medi + stdv * gdat.thrssigmflar
                            indxtimeposi = np.where(listmdetflar > gdat.thrssigmflar)[0]
                        
                        
                        for n in range(len(indxtimeposi)):
                            if (n == len(indxtimeposi) - 1) or (n < len(indxtimeposi) - 1) and not ((indxtimeposi[n] + 1) in indxtimeposi):
                                gdat.listindxtimeflar[p][y].append(indxtimeposi[n])
                                mdetflar = listmdetflar[indxtimeposi[n]]
                                gdat.listmdetflar[p][y].append(mdetflar)
                        gdat.listindxtimeflar[p][y] = np.array(gdat.listindxtimeflar[p][y])
                        gdat.listmdetflar[p][y] = np.array(gdat.listmdetflar[p][y])

                    if gdat.typemodlflar == 'tmpl':
                        dictsrchflaroutp = ephesos.srch_flar(gdat.arrytser['bdtr'][0][p][:, 0], gdat.arrytser['bdtr'][0][p][:, 1], **dictsrchflarinpt)
                
            gdat.dictmileoutp['listindxtimeflar'] = gdat.listindxtimeflar
            gdat.dictmileoutp['listmdetflar'] = gdat.listmdetflar
            gdat.dictmileoutp['precphot'] = gdat.precphot
            
            for p in gdat.indxinst[0]:
                for y in gdat.indxchun[0][p]:
                    if gdat.boolplottser:
                        plot_tser(gdat, strgmodl, 0, p, y, 'bdtr', boolflar=True)
                if gdat.boolplottser:
                    plot_tser(gdat, strgmodl, 0, p, None, 'bdtr', boolflar=True)
            
            if gdat.typeverb > 0:
                print('temp: skipping masking out of flaress...')
            # mask out flares
            #numbkern = len(maxmcorr)
            #indxkern = np.arange(numbkern)
            #listindxtimemask = []
            #for k in indxkern:
            #    for indxtime in gdat.listindxtimeposimaxm[k]:
            #        indxtimemask = np.arange(indxtime - 60, indxtime + 60)
            #        listindxtimemask.append(indxtimemask)
            #indxtimemask = np.concatenate(listindxtimemask)
            #indxtimemask = np.unique(indxtimemask)
            #indxtimegood = np.setdiff1d(np.arange(gdat.time.size), indxtimemask)
            #gdat.time = gdat.time[indxtimegood]
            #gdat.lcurdata = gdat.lcurdata[indxtimegood]
            #gdat.lcurdatastdv = gdat.lcurdatastdv[indxtimegood]
            #gdat.numbtime = gdat.time.size

    if gdat.booltserdata:
        if gdat.boolinfe and (gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'psyspcur' or gdat.fitt.typemodl == 'psysttvr'):
            gdat.numbcompprio = gdat.epocmtracompprio.size
            gdat.indxcompprio = np.arange(gdat.numbcompprio)

    print('gdat.numbcompprio')
    print(gdat.numbcompprio)

    if gdat.labltarg == 'WASP-43' and gdat.numbcompprio is None:
        print('gdat.boolinfe')
        print(gdat.boolinfe)
        print('gdat.fitt.typemodl')
        print(gdat.fitt.typemodl)
        raise Exception('')
        
    # data validation (DV) report
    ## number of pages in the DV report
    if gdat.boolplot:
        gdat.numbpage = 1
        if gdat.numbcompprio is not None:
            gdat.numbpage += gdat.numbcompprio
        
        gdat.indxpage = np.arange(gdat.numbpage)
        
        if gdat.numbcompprio is not None:
            for j in gdat.indxcompprio:
                gdat.listdictdvrp.append([])
    
        # add pbox plots to the DV report
        if gdat.boolsrchpbox and gdat.boolplot:
            for p in gdat.indxinst[0]:
                for g, name in enumerate(['sigr', 'resisigr', 'stdvresisigr', 'sdeecomp', 'pcur', 'rflx']):
                    for j in range(len(dictpboxoutp['epocmtracomp'])):
                        gdat.listdictdvrp[j+1].append({'path': dictpboxoutp['listpathplot%s' % name][j], 'limt':[0., 0.9 - g * 0.1, 0.5, 0.1]})
    
    gdat.dictmileoutp['numbcompprio'] = gdat.numbcompprio
    
    # calculate LS periodogram
    if gdat.boolcalclspe:
        if gdat.boolplot:
            pathvisulspe = gdat.pathvisutarg
        else:
            pathvisulspe = None

        liststrgarrylspe = ['raww']
        if gdat.boolbdtranyy:
            liststrgarrylspe += ['bdtr']
        for b in gdat.indxdatatser:
            
            # temp -- neglects LS periodograms of RV data
            if b == 1:
                continue
            
            if gdat.numbinst[b] > 0:
                
                for e in gdat.indxdataiter:
                    if gdat.numbinst[b] > 1:
                        strgextn = '%s%s_%s' % (gdat.liststrgtser[b], gdat.liststrgdataiter[e], gdat.strgtarg)
                        gdat.dictlspeoutp = exec_lspe(gdat.arrytsertotl[b][:, e, :], pathvisu=pathvisulspe, strgextn=strgextn, maxmfreq=maxmfreqlspe, \
                                                                                  typeverb=gdat.typeverb, typefileplot=gdat.typefileplot, pathdata=gdat.pathdatatarg)
                    
                    for p in gdat.indxinst[b]:
                        for strg in liststrgarrylspe:
                            strgextn = '%s_%s_%s%s_%s' % (strg, gdat.liststrgtser[b], gdat.liststrginst[b][p], gdat.liststrgdataiter[e], gdat.strgtarg) 
                            gdat.dictlspeoutp = exec_lspe(gdat.arrytser[strg][b][p][:, e, :], pathvisu=pathvisulspe, strgextn=strgextn, maxmfreq=maxmfreqlspe, \
                                                                                  typeverb=gdat.typeverb, typefileplot=gdat.typefileplot, pathdata=gdat.pathdatatarg)
        
                    gdat.dictmileoutp['perilspempow'] = gdat.dictlspeoutp['perimpow']
                    gdat.dictmileoutp['powrlspempow'] = gdat.dictlspeoutp['powrmpow']
                    
                    if gdat.boolplot:
                        gdat.listdictdvrp[0].append({'path': gdat.dictlspeoutp['pathplot'], 'limt':[0., 0.8, 0.5, 0.1]})
        
    if gdat.booltserdata and gdat.boolmodltran:
        if gdat.liststrgcomp is None:
            gdat.liststrgcomp = ephesos.retr_liststrgcomp(gdat.numbcompprio)
        if gdat.listcolrcomp is None:
            gdat.listcolrcomp = ephesos.retr_listcolrcomp(gdat.numbcompprio)
        
        if gdat.typeverb > 0:
            print('Planet letters: ')
            print(gdat.liststrgcomp)
    
        if gdat.duraprio is None:
            
            if gdat.booldiag and (gdat.pericompprio is None or gdat.rsmacompprio is None or gdat.cosicompprio is None):
                print('gdat.pericompprio')
                print(gdat.pericompprio)
                print('gdat.rsmacompprio')
                print(gdat.rsmacompprio)
                print('gdat.cosicompprio')
                print(gdat.cosicompprio)
                raise Exception('')

            gdat.duraprio = ephesos.retr_duratran(gdat.pericompprio, gdat.rsmacompprio, gdat.cosicompprio)
        
        if gdat.rratcompprio is None:
            gdat.rratcompprio = np.sqrt(1e-3 * gdat.deptprio)
        if gdat.rsmacompprio is None:
            gdat.rsmacompprio = np.sqrt(np.sin(np.pi * gdat.duraprio / gdat.pericompprio / 24.)**2 + gdat.cosicompprio**2)
        print('gdat.ecoscompprio')
        print(gdat.ecoscompprio)
        if gdat.ecoscompprio is None:
            gdat.ecoscompprio = np.zeros(gdat.numbcompprio)
        print('gdat.ecoscompprio')
        print(gdat.ecoscompprio)
        if gdat.esincompprio is None:
            if gdat.booldiag:
                if gdat.numbcompprio is None:
                    print('')
                    print('')
                    print('')
                    print('gdat.numbcompprio is None')
                    raise Exception('')
            gdat.esincompprio = np.zeros(gdat.numbcompprio)
        if gdat.rvelsemaprio is None:
            gdat.rvelsemaprio = np.zeros(gdat.numbcompprio)
        
        if gdat.stdvrratcompprio is None:
            gdat.stdvrratcompprio = 0.01 + np.zeros(gdat.numbcompprio)
        if gdat.stdvrsmacompprio is None:
            gdat.stdvrsmacompprio = 0.01 + np.zeros(gdat.numbcompprio)
        if gdat.stdvepocmtracompprio is None:
            gdat.stdvepocmtracompprio = 0.1 + np.zeros(gdat.numbcompprio)
        if gdat.stdvpericompprio is None:
            gdat.stdvpericompprio = 0.01 + np.zeros(gdat.numbcompprio)
        if gdat.stdvcosicompprio is None:
            gdat.stdvcosicompprio = 0.05 + np.zeros(gdat.numbcompprio)
        if gdat.stdvecoscompprio is None:
            gdat.stdvecoscompprio = 0.1 + np.zeros(gdat.numbcompprio)
        if gdat.stdvesincompprio is None:
            gdat.stdvesincompprio = 0.1 + np.zeros(gdat.numbcompprio)
        if gdat.stdvrvelsemaprio is None:
            gdat.stdvrvelsemaprio = 0.001 + np.zeros(gdat.numbcompprio)
        
        # others
        if gdat.projoblqprio is None:
            gdat.projoblqprio = 0. + np.zeros(gdat.numbcompprio)
        if gdat.stdvprojoblqprio is None:
            gdat.stdvprojoblqprio = 10. + np.zeros(gdat.numbcompprio)
        
        # order planets with respect to period
        if gdat.typepriocomp != 'inpt':
            
            if gdat.typeverb > 0:
                print('Sorting the planets with respect to orbital period...')
            
            indxcompsort = np.argsort(gdat.pericompprio)
            
            #gdat.booltrancomp = gdat.booltrancomp[indxcompsort]
            gdat.rratcompprio = gdat.rratcompprio[indxcompsort]
            gdat.rsmacompprio = gdat.rsmacompprio[indxcompsort]
            gdat.epocmtracompprio = gdat.epocmtracompprio[indxcompsort]
            gdat.pericompprio = gdat.pericompprio[indxcompsort]
            gdat.cosicompprio = gdat.cosicompprio[indxcompsort]
            print('gdat.numbcompprio')
            print(gdat.numbcompprio)
            print('gdat.ecoscompprio')
            print(gdat.ecoscompprio)
            gdat.ecoscompprio = gdat.ecoscompprio[indxcompsort]
            gdat.esincompprio = gdat.esincompprio[indxcompsort]
            gdat.rvelsemaprio = gdat.rvelsemaprio[indxcompsort]
        
            gdat.duraprio = gdat.duraprio[indxcompsort]
        
        # if stellar features are NaN, use Solar defaults
        for featstar in gdat.listfeatstar:
            if not hasattr(gdat, featstar) or getattr(gdat, featstar) is None or not np.isfinite(getattr(gdat, featstar)):
                if featstar == 'radistar':
                    setattr(gdat, featstar, 1.)
                if featstar == 'massstar':
                    setattr(gdat, featstar, 1.)
                if featstar == 'tmptstar':
                    setattr(gdat, featstar, 5778.)
                if featstar == 'vsiistar':
                    setattr(gdat, featstar, 1e3)
                if gdat.typeverb > 0:
                    print('Setting %s to the Solar value!' % featstar)

        # if stellar feature uncertainties are NaN, use 10%
        for featstar in gdat.listfeatstar:
            if (not hasattr(gdat, 'stdv' + featstar) or getattr(gdat, 'stdv' + featstar) is None or not np.isfinite(getattr(gdat, 'stdv' + featstar))) \
                                                                        and not (featstar == 'rascstar' or featstar == 'declstar'):
                varb = hasattr(gdat, featstar)
                if varb is not None:
                    setattr(gdat, 'stdv' + featstar, 0.5 * varb)
                if gdat.typeverb > 0:
                    print('Setting %s uncertainty to 50%%!' % featstar)

        gdat.radicompprio = gdat.rratcompprio * gdat.radistar
        
        if gdat.typeverb > 0:
            
            if gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'psyspcur':
                print('Stellar priors:')
                print('gdat.rascstar')
                print(gdat.rascstar)
                print('gdat.declstar')
                print(gdat.declstar)
                print('gdat.radistar [R_S]')
                print(gdat.radistar)
                print('gdat.stdvradistar [R_S]')
                print(gdat.stdvradistar)
                print('gdat.massstar')
                print(gdat.massstar)
                print('gdat.stdvmassstar')
                print(gdat.stdvmassstar)
                print('gdat.vsiistar')
                print(gdat.vsiistar)
                print('gdat.stdvvsiistar')
                print(gdat.stdvvsiistar)
                print('gdat.massstar [M_S]')
                print(gdat.massstar)
                print('gdat.stdvmassstar [M_S]')
                print(gdat.stdvmassstar)
                print('gdat.tmptstar')
                print(gdat.tmptstar)
                print('gdat.stdvtmptstar')
                print(gdat.stdvtmptstar)
                
                print('Planetary priors:')
                print('gdat.duraprio')
                print(gdat.duraprio)
                print('gdat.deptprio')
                print(gdat.deptprio)
                print('gdat.rratcompprio')
                print(gdat.rratcompprio)
                print('gdat.rsmacompprio')
                print(gdat.rsmacompprio)
                print('gdat.epocmtracompprio')
                print(gdat.epocmtracompprio)
                print('gdat.pericompprio')
                print(gdat.pericompprio)
                print('gdat.cosicompprio')
                print(gdat.cosicompprio)
                print('gdat.ecoscompprio')
                print(gdat.ecoscompprio)
                print('gdat.esincompprio')
                print(gdat.esincompprio)
                print('gdat.rvelsemaprio')
                print(gdat.rvelsemaprio)
                print('gdat.stdvrratcompprio')
                print(gdat.stdvrratcompprio)
                print('gdat.stdvrsmacompprio')
                print(gdat.stdvrsmacompprio)
                print('gdat.stdvepocmtracompprio')
                print(gdat.stdvepocmtracompprio)
                print('gdat.stdvpericompprio')
                print(gdat.stdvpericompprio)
                print('gdat.stdvcosicompprio')
                print(gdat.stdvcosicompprio)
                print('gdat.stdvecoscompprio')
                print(gdat.stdvecoscompprio)
                print('gdat.stdvesincompprio')
                print(gdat.stdvesincompprio)
                print('gdat.stdvrvelsemaprio')
                print(gdat.stdvrvelsemaprio)
        
                if not np.isfinite(gdat.rratcompprio).all():
                    print('rrat is infinite!')
                if not np.isfinite(gdat.rsmacompprio).all():
                    print('rsma is infinite!')
                if not np.isfinite(gdat.epocmtracompprio).all():
                    print('epoc is infinite!')
                if not np.isfinite(gdat.pericompprio).all():
                    print('peri is infinite!')
                if not np.isfinite(gdat.cosicompprio).all():
                    print('cosi is infinite!')
                if not np.isfinite(gdat.ecoscompprio).all():
                    print('ecos is infinite!')
                if not np.isfinite(gdat.esincompprio).all():
                    print('esin is infinite!')
                if not np.isfinite(gdat.rvelsemaprio).all():
                    print('rvelsema is infinite!')

        # carry over RV data as is, without any detrending
        gdat.arrytser['bdtr'][1] = gdat.arrytser['raww'][1]
        gdat.listarrytser['bdtr'][1] = gdat.listarrytser['raww'][1]
        
        if gdat.booldiag:
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for y in gdat.indxchun[b][p]:
                        if len(gdat.listarrytser['bdtr'][b][p][y]) == 0:
                            print('bpy')
                            print(b, p, y)
                            raise Exception('')
            
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if not np.isfinite(gdat.arrytser['bdtr'][b][p]).all():
                        print('b, p')
                        print(b, p)
                        indxbadd = np.where(~np.isfinite(gdat.arrytser['bdtr'][b][p]))[0]
                        print('gdat.arrytser[bdtr][b][p]')
                        summgene(gdat.arrytser['bdtr'][b][p])
                        print('indxbadd')
                        summgene(indxbadd)
                        raise Exception('')
        
        # determine times during transits
        gdat.listindxtimeoutt = [[[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser] for j in gdat.indxcompprio]
        gdat.listindxtimetranindi = [[[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser] for j in gdat.indxcompprio]
        gdat.listindxtimetran = [[[[[] for m in range(2)] for p in gdat.indxinst[b]] for b in gdat.indxdatatser] for j in gdat.indxcompprio]
        gdat.listindxtimetranchun = [[[[[] for y in gdat.indxchun[b][p]] for p in gdat.indxinst[b]] for b in gdat.indxdatatser] for j in gdat.indxcompprio]
        gdat.listindxtimeclen = [[[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser] for j in gdat.indxcompprio]
        gdat.numbtimeclen = [[np.empty((gdat.numbcompprio), dtype=int) for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        
        gdat.numbtran = np.empty(gdat.numbcompprio, dtype=int)
        for j in gdat.indxcompprio:
            gdat.listtimeconc = []
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    if not np.isfinite(gdat.duraprio[j]):
                        continue
                    # determine time mask
                    for y in gdat.indxchun[b][p]:
                        gdat.listindxtimetranchun[j][b][p][y] = ephesos.retr_indxtimetran(gdat.listarrytser['bdtr'][b][p][y][:, 0, 0], \
                                                                                               gdat.epocmtracompprio[j], gdat.pericompprio[j], gdat.duraprio[j])
                    
                    # primary
                    gdat.listindxtimetran[j][b][p][0] = ephesos.retr_indxtimetran(gdat.arrytser['bdtr'][b][p][:, 0, 0], \
                                                                                             gdat.epocmtracompprio[j], gdat.pericompprio[j], gdat.duraprio[j])
                    
                    # primary individuals
                    gdat.listindxtimetranindi[j][b][p] = ephesos.retr_indxtimetran(gdat.arrytser['bdtr'][b][p][:, 0, 0], \
                                                                                      gdat.epocmtracompprio[j], gdat.pericompprio[j], gdat.duraprio[j], boolindi=True)
                    
                    # secondary
                    gdat.listindxtimetran[j][b][p][1] = ephesos.retr_indxtimetran(gdat.arrytser['bdtr'][b][p][:, 0, 0], \
                                                                         gdat.epocmtracompprio[j], gdat.pericompprio[j], gdat.duraprio[j], boolseco=True)
                    
                    gdat.listindxtimeoutt[j][b][p] = np.setdiff1d(np.arange(gdat.arrytser['bdtr'][b][p].shape[0]), gdat.listindxtimetran[j][b][p][0])
                    
                    gdat.listtimeconc.append(gdat.arrytser['bdtr'][b][p][:, 0, 0])
            
            if len(gdat.listtimeconc) > 0:
                gdat.listtimeconc = np.concatenate(gdat.listtimeconc)
                gdat.listindxtran = ephesos.retr_indxtran(gdat.listtimeconc, gdat.epocmtracompprio[j], gdat.pericompprio[j], gdat.duraprio[j])
                gdat.numbtran[j] = len(gdat.listindxtran)
        
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                for j in gdat.indxcompprio:
                    # clean times for each planet
                    listindxtimetemp = []
                    for jj in gdat.indxcompprio:
                        if jj != j:
                            listindxtimetemp.append(gdat.listindxtimetran[jj][b][p][0])
                    if len(listindxtimetemp) > 0:
                        listindxtimetemp = np.concatenate(listindxtimetemp)
                        listindxtimetemp = np.unique(listindxtimetemp)
                    else:
                        listindxtimetemp = np.array([])
                    gdat.listindxtimeclen[j][b][p] = np.setdiff1d(np.arange(gdat.arrytser['bdtr'][b][p].shape[0]), listindxtimetemp)
                    gdat.numbtimeclen[b][p][j] = gdat.listindxtimeclen[j][b][p].size
                    
        # ingress and egress times
        if gdat.fitt.typemodl == 'psysdisktran':
            gdat.fracineg = np.zeros(2)
            gdat.listindxtimetranineg = [[[[[] for k in range(4)] for p in gdat.indxinst[b]] for b in gdat.indxdatatser] for j in gdat.indxcompprio]
            gdat.durafullprio = (1. - gdat.rratcompprio) / (1. + gdat.rratcompprio) * gdat.duraprio
            for p in gdat.indxinst[0]:
                for j in gdat.indxcompprio:
                    if not gdat.booltrancomp[j]:
                        continue

                    gdat.listindxtimetranineg[j][0][p][0] = ephesos.retr_indxtimetran(gdat.arrytser['bdtr'][0][p][:, 0, 0], gdat.epocmtracompprio[j], gdat.pericompprio[j], \
                                                                                                  gdat.duraprio[j], durafull=gdat.durafullprio[j], typeineg='ingrinit')
                    gdat.listindxtimetranineg[j][0][p][1] = ephesos.retr_indxtimetran(gdat.arrytser['bdtr'][0][p][:, 0, 0], gdat.epocmtracompprio[j], gdat.pericompprio[j], \
                                                                                                  gdat.duraprio[j], durafull=gdat.durafullprio[j], typeineg='ingrfinl')
                    gdat.listindxtimetranineg[j][0][p][2] = ephesos.retr_indxtimetran(gdat.arrytser['bdtr'][0][p][:, 0, 0], gdat.epocmtracompprio[j], gdat.pericompprio[j], \
                                                                                                  gdat.duraprio[j], durafull=gdat.durafullprio[j], typeineg='eggrinit')
                    gdat.listindxtimetranineg[j][0][p][3] = ephesos.retr_indxtimetran(gdat.arrytser['bdtr'][0][p][:, 0, 0], gdat.epocmtracompprio[j], gdat.pericompprio[j], \
                                                                                                  gdat.duraprio[j], durafull=gdat.durafullprio[j], typeineg='eggrfinl')
                    
                    for k in range(2):
                        indxtimefrst = gdat.listindxtimetranineg[j][0][p][2*k+0]
                        indxtimeseco = gdat.listindxtimetranineg[j][0][p][2*k+1]
                        if indxtimefrst.size == 0 or indxtimeseco.size == 0:
                            continue
                        rflxinit = np.mean(gdat.arrytser['bdtr'][0][p][indxtimefrst, 1])
                        rflxfinl = np.mean(gdat.arrytser['bdtr'][0][p][indxtimeseco, 1])
                        gdat.fracineg[k] = rflxinit / rflxfinl
                    if (gdat.fracineg == 0).any():
                        print('rflxinit')
                        print(rflxinit)
                        print('rflxfinl')
                        print(rflxfinl)
                        print('gdat.arrytser[bdtr][0][p]')
                        summgene(gdat.arrytser['bdtr'][0][p])
                        print('gdat.arrytser[bdtrnotr][0][p][:, 1]')
                        summgene(gdat.arrytser['bdtr'][0][p][:, 1])
                        print('gdat.arrytser[bdtrnotr][0][p][indxtimefrst, 1]')
                        summgene(gdat.arrytser['bdtr'][0][p][indxtimefrst, 1])
                        print('gdat.arrytser[bdtrnotr][0][p][indxtimeseco, 1]')
                        summgene(gdat.arrytser['bdtr'][0][p][indxtimeseco, 1])
                        raise Exception('')

                    path = gdat.pathdatatarg + 'fracineg%04d.csv' % j
                    np.savetxt(path, gdat.fracineg, delimiter=',')
                    gdat.dictmileoutp['fracineg%04d' % j] = gdat.fracineg
        
        if gdat.listindxchuninst is None:
            gdat.listindxchuninst = [gdat.indxchun]
    
        # plot raw data
        #if gdat.typetarg != 'inpt' and 'TESS' in gdat.liststrginst[0] and gdat.listarrytsersapp is not None:
        #    for b in gdat.indxdatatser:
        #        for p in gdat.indxinst[b]:
        #            if gdat.liststrginst[b][p] != 'TESS':
        #                continue
        #            for y in gdat.indxchun[b][p]:
        #                path = gdat.pathdatatarg + gdat.liststrgchun[b][p][y] + '_SAP.csv'
        #                if not os.path.exists(path):
        #                    if gdat.typeverb > 0:
        #                        print('Writing to %s...' % path)
        #                    np.savetxt(path, gdat.listarrytsersapp[y], delimiter=',', header='time,flux,flux_err')
        #                path = gdat.pathdatatarg + gdat.liststrgchun[b][p][y] + '_PDCSAP.csv'
        #                if not os.path.exists(path):
        #                    if gdat.typeverb > 0:
        #                        print('Writing to %s...' % path)
        #                    np.savetxt(path, gdat.listarrytserpdcc[y], delimiter=',', header='time,flux,flux_err')
        #    
        #    # plot PDCSAP and SAP light curves
        #    figr, axis = plt.subplots(2, 1, figsize=gdat.figrsizeydob)
        #    axis[0].plot(gdat.arrytsersapp[:, 0] - gdat.timeoffs, gdat.arrytsersapp[:, 1], color='k', marker='.', ls='', ms=1, rasterized=True)
        #    axis[1].plot(gdat.arrytserpdcc[:, 0] - gdat.timeoffs, gdat.arrytserpdcc[:, 1], color='k', marker='.', ls='', ms=1, rasterized=True)
        #    #axis[0].text(.97, .97, 'SAP', transform=axis[0].transAxes, size=20, color='r', ha='right', va='top')
        #    #axis[1].text(.97, .97, 'PDC', transform=axis[1].transAxes, size=20, color='r', ha='right', va='top')
        #    axis[1].set_xlabel('Time [BJD - %d]' % gdat.timeoffs)
        #    for a in range(2):
        #        axis[a].set_ylabel(gdat.labltserphot)
        #    
        #    plt.subplots_adjust(hspace=0.)
        #    path = gdat.pathvisutarg + 'lcurspoc_%s.%s' % (gdat.strgtarg, gdat.typefileplot)
        #    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0.4, 0.05, 0.8, 0.8]})
        #    if gdat.typeverb > 0:
        #        print('Writing to %s...' % path)
        #    plt.savefig(path)
        #    plt.close()
        
    # calculate the visibility of the target
    if gdat.boolcalcvisi:
        
        if gdat.listdelttimeobvtyear is None:
            gdat.listdelttimeobvtyear = np.linspace(0., 365., 10000)

        massairr = tdpy.calc_visitarg(gdat.rasctarg, gdat.decltarg, gdat.latiobvt, gdat.longobvt, gdat.strgtimeobvtyear, gdat.listdelttimeobvtyear, gdat.heigobvt)

        gdat.dictmileoutp['massairr'] = massairr

        # alt-az coordinate object for the Sun
        #objtcoorsunnalazyear = astropy.coordinates.get_sun(objttimeyear)
        #objtcoorsunnalazyear = objtcoorsunnalazyear.transform_to(objtframobvtyear)
            
        # quantities during a given night
        if gdat.strgtimeobvtnigh is not None:
            objttimenigh = astropy.time.Time(astropy.time.Time(gdat.strgtimeobvtnigh).jd, format='jd', location=objtlocaobvt)
            objttimenighcent = astropy.time.Time(int(objttimenigh.jd), format='jd', location=objtlocaobvt)
            objttimenighcen1 = astropy.time.Time(int(objttimenigh.jd + 1), format='jd', location=objtlocaobvt)
            objttimenigh = objttimenighcent + (12. + timedelt - gdat.offstimeobvt) * astropy.units.hour
        
            # frame object for the observatory during the selected night
            objtframobvtnigh = astropy.coordinates.AltAz(obstime=objttimenigh, location=objtlocaobvt)
        
            # alt-az coordinate object for the Sun
            objtcoorsunnalaznigh = astropy.coordinates.get_sun(objttimenigh).transform_to(objtframobvtnigh)
            # alt-az coordinate object for the Moon
            objtcoormoonalaznigh = astropy.coordinates.get_moon(objttimenigh).transform_to(objtframobvtnigh)
            # alt-az coordinate object for the target
            objtcoorplanalaznigh = astropy.coordinates.SkyCoord(ra=gdat.rasctarg, dec=gdat.decltarg, frame='icrs', unit='deg').transform_to(objtframobvtnigh)
        
            # air mass of the target during the night
            massairr = objtcoorplanalaznigh.secz
        
            for j in gmod.indxcomp:
                indx = ephesos.retr_indxtimetran(timeyear, gdat.epocmtracompprio[j], gdat.pericompprio[j], gdat.duraprio[j])
                
                import operator
                import itertools
                for k, g in itertools.groupby(enumerate(list(indx)), lambda ix : ix[0] - ix[1]):
                    print(map(operator.itemgetter(1), g))
            
            labltime = 'Local time to Midnight [hour]'
            print('%s, Air mass' % labltime)
            for ll in range(len(massairr)):
                print('%6g %6.3g' % (timedelt[ll], massairr[ll]))

            
    # plot visibility of the target
    if gdat.boolplotvisi:
        strgtitl = '%s, %s/%s' % (gdat.labltarg, objttimenighcent.iso[:10], objttimenighcen1.iso[:10])

        # plot air mass
        figr, axis = plt.subplots(figsize=(8, 4))
        
        indx = np.where(np.isfinite(massairr) & (massairr > 0))[0]
        plt.plot(timedelt[indx], massairr[indx])
        axis.fill_between(timedelt, 0, 90, objtcoorsunnalaznigh.alt < -0*astropy.units.deg, color='0.5', zorder=0)
        axis.fill_between(timedelt, 0, 90, objtcoorsunnalaznigh.alt < -18*astropy.units.deg, color='k', zorder=0)
        axis.fill_between(timedelt, 0, 90, (massairr > 2.) | (massairr < 1.), color='r', alpha=0.3, zorder=0)
        axis.set_xlabel(labltime)
        axis.set_ylabel('Airmass')
        limtxdat = [np.amin(timedelt), np.amax(timedelt)]
        axis.set_title(strgtitl)
        axis.set_xlim(limtxdat)
        axis.set_ylim([1., 2.])
        path = gdat.pathvisutarg + 'airmass_%s.%s' % (gdat.strgtarg, gdat.typefileplot)
        print('Writing to %s...' % path)
        plt.savefig(path)
        
        # plot altitude
        figr, axis = plt.subplots(figsize=(8, 4))
        axis.plot(timedelt, objtcoorsunnalaznigh.alt, color='orange', label='Sun')
        axis.plot(timedelt, objtcoormoonalaznigh.alt, color='gray', label='Moon')
        axis.plot(timedelt, objtcoorplanalaznigh.alt, color='blue', label=gdat.labltarg)
        axis.fill_between(timedelt, 0, 90, objtcoorsunnalaznigh.alt < -0*astropy.units.deg, color='0.5', zorder=0)
        axis.fill_between(timedelt, 0, 90, objtcoorsunnalaznigh.alt < -18*astropy.units.deg, color='k', zorder=0)
        axis.fill_between(timedelt, 0, 90, (massairr > 2.) | (massairr < 1.), color='r', alpha=0.3, zorder=0)
        axis.legend(loc='upper left')
        plt.ylim([0, 90])
        axis.set_title(strgtitl)
        axis.set_xlim(limtxdat)
        axis.set_xlabel(labltime)
        axis.set_ylabel('Altitude [deg]')
        
        path = gdat.pathvisutarg + 'altitude_%s.%s' % (gdat.strgtarg, gdat.typefileplot)
        print('Writing to %s...' % path)
        plt.savefig(path)

    ### bin the light curve
    if gdat.booltserdata:
        pass
        #gdat.delttimebind = 1. # [days]
        #for b in gdat.indxdatatser:
        #    for p in gdat.indxinst[b]:
        #        gdat.arrytser['bdtrbind'][b][p] = ephesos.rebn_tser(gdat.arrytser['bdtr'][b][p], delt=gdat.delttimebind)
        #        for y in gdat.indxchun[b][p]:
        #            gdat.listarrytser['bdtrbind'][b][p][y] = ephesos.rebn_tser(gdat.listarrytser['bdtr'][b][p][y], delt=gdat.delttimebind)
        #            
        #            path = gdat.pathdatatarg + 'arrytserbdtrbind%s%s.csv' % (gdat.liststrginst[b][p], gdat.liststrgchun[b][p][y])
        #            if not os.path.exists(path):
        #                if gdat.typeverb > 0:
        #                    print('Writing to %s' % path)
        #                np.savetxt(path, gdat.listarrytser['bdtrbind'][b][p][y], delimiter=',', \
        #                                                header='time,%s,%s_err' % (gdat.liststrgtsercsvv[b], gdat.liststrgtsercsvv[b]))
        #        
        #            if gdat.boolplottser:
        #                plot_tser(gdat, strgmodl, b, p, y, 'bdtrbind')
                
    

        gdat.dictmileoutp['boolposianls'] = np.empty(gdat.numbtypeposi, dtype=bool)
        if gdat.boolsrchpbox:
            gdat.dictmileoutp['boolposianls'][0] = dictpboxoutp['sdeecomp'][0] > gdat.thrssdeecosc
        if gdat.boolcalclspe:
            gdat.dictmileoutp['boolposianls'][1] = gdat.dictmileoutp['powrlspempow'] > gdat.thrslspecosc
        gdat.dictmileoutp['boolposianls'][2] = gdat.dictmileoutp['boolposianls'][0] or gdat.dictmileoutp['boolposianls'][1]
        gdat.dictmileoutp['boolposianls'][3] = gdat.dictmileoutp['boolposianls'][0] and gdat.dictmileoutp['boolposianls'][1]
        
        for strgmodl in gdat.liststrgmodl:
            gmod = getattr(gdat, strgmodl)

            if gdat.boolinfe and gmod.boolmodlpcur:
                ### Doppler beaming
                if gdat.typeverb > 0:
                    print('Assuming TESS passband for estimating Dopller beaming...')
                gdat.binswlenbeam = np.linspace(0.6, 1., 101)
                gdat.meanwlenbeam = (gdat.binswlenbeam[1:] + gdat.binswlenbeam[:-1]) / 2.
                gdat.diffwlenbeam = (gdat.binswlenbeam[1:] - gdat.binswlenbeam[:-1]) / 2.
                x = 2.248 / gdat.meanwlenbeam
                gdat.funcpcurmodu = .25 * x * np.exp(x) / (np.exp(x) - 1.)
                gdat.consbeam = np.sum(gdat.diffwlenbeam * gdat.funcpcurmodu)

                #if ''.join(gdat.liststrgcomp) != ''.join(sorted(gdat.liststrgcomp)):
                #if gdat.typeverb > 0:
                #       print('Provided planet letters are not in order. Changing the TCE order to respect the letter order in plots (b, c, d, e)...')
                #    gmod.indxcomp = np.argsort(np.array(gdat.liststrgcomp))

    gdat.liststrgcompfull = np.empty(gdat.numbcompprio, dtype='object')
    if gdat.numbcompprio is not None:
        for j in gdat.indxcompprio:
            print('gdat.numbcompprio')
            print(gdat.numbcompprio)
            print('gdat.indxcompprio')
            summgene(gdat.indxcompprio)
            print('gdat.liststrgcomp')
            print(gdat.liststrgcomp)
            print('gdat.liststrgcompfull')
            print(gdat.liststrgcompfull)
            gdat.liststrgcompfull[j] = gdat.labltarg + ' ' + gdat.liststrgcomp[j]

    ## augment object dictinary
    gdat.dictfeatobjt = dict()
    if gdat.numbcompprio is not None:
        gdat.dictfeatobjt['namestar'] = np.array([gdat.labltarg] * gdat.numbcompprio)
        gdat.dictfeatobjt['nameplan'] = gdat.liststrgcompfull
        # temp
        gdat.dictfeatobjt['booltran'] = np.array([True] * gdat.numbcompprio, dtype=bool)
    for namemagt in ['vmag', 'jmag', 'hmag', 'kmag']:
        magt = getattr(gdat, '%ssyst' % namemagt)
        if magt is not None:
            gdat.dictfeatobjt['%ssyst' % namemagt] = np.zeros(gdat.numbcompprio) + magt
    if gdat.numbcompprio is not None:
        gdat.dictfeatobjt['numbplanstar'] = np.zeros(gdat.numbcompprio) + gdat.numbcompprio
        gdat.dictfeatobjt['numbplantranstar'] = np.zeros(gdat.numbcompprio) + gdat.numbcompprio
    
    if gdat.booltserdata:
        if gdat.boolinfe and gmod.boolmodlpcur:
            if gdat.dilu == 'lygos':
                if gdat.typeverb > 0:
                    print('Calculating the contamination ratio...')
                gdat.contrati = lygos.retr_contrati()

            # correct for dilution
            #if gdat.typeverb > 0:
            #print('Correcting for dilution!')
            #if gdat.dilucorr is not None:
            #    gdat.arrytserdilu = np.copy(gdat.listarrytser['bdtr'][b][p][y])
            #if gdat.dilucorr is not None:
            #    gdat.arrytserdilu[:, 1] = 1. - gdat.dilucorr * (1. - gdat.listarrytser['bdtr'][b][p][y][:, 1])
            #gdat.arrytserdilu[:, 1] = 1. - gdat.contrati * gdat.contrati * (1. - gdat.listarrytser['bdtr'][b][p][y][:, 1])
            
            ## phase-fold and save the baseline-detrended light curve
            gdat.numbbinspcurtotl = 100
            gdat.delttimebindzoom = gdat.duraprio / 24. / 50.
            gdat.arrypcur = dict()

            gdat.arrypcur['quadbdtr'] = [[[[] for j in gdat.indxcompprio] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            gdat.arrypcur['quadbdtrbindtotl'] = [[[[] for j in gdat.indxcompprio] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            gdat.arrypcur['primbdtr'] = [[[[] for j in gdat.indxcompprio] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            gdat.arrypcur['primbdtrbindtotl'] = [[[[] for j in gdat.indxcompprio] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            gdat.arrypcur['primbdtrbindzoom'] = [[[[] for j in gdat.indxcompprio] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
            gdat.liststrgpcur = ['bdtr', 'resi', 'modl']
            gdat.liststrgpcurcomp = ['modltotl', 'modlstel', 'modlplan', 'modlelli', 'modlpmod', 'modlnigh', 'modlbeam', 'bdtrplan']
            gdat.binsphasprimtotl = np.linspace(-0.5, 0.5, gdat.numbbinspcurtotl + 1)
            gdat.binsphasquadtotl = np.linspace(-0.25, 0.75, gdat.numbbinspcurtotl + 1)
            gdat.numbbinspcurzoom = (gdat.pericompprio / gdat.delttimebindzoom).astype(int)
            gdat.binsphasprimzoom = [[] for j in gdat.indxcompprio]
            for j in gdat.indxcompprio:
                if np.isfinite(gdat.duraprio[j]):
                    gdat.binsphasprimzoom[j] = np.linspace(-0.5, 0.5, gdat.numbbinspcurzoom[j] + 1)

            if gdat.typeverb > 0:
                print('Phase folding and binning the light curve...')
            for b in gdat.indxdatatser:
                for p in gdat.indxinst[b]:
                    for j in gdat.indxcompprio:

                        gdat.arrypcur['primbdtr'][b][p][j] = ephesos.fold_tser(gdat.arrytser['bdtr'][b][p][gdat.listindxtimeclen[j][b][p], :, :], \
                                                                                                                gdat.epocmtracompprio[j], gdat.pericompprio[j])
                        
                        if gdat.arrypcur['primbdtr'][b][p][j].ndim > 3:
                            print('')
                            print('gdat.arrytser[bdtr][b][p][gdat.listindxtimeclen[j][b][p], :, :]')
                            summgene(gdat.arrytser['bdtr'][b][p][gdat.listindxtimeclen[j][b][p], :, :])
                            print('gdat.arrypcur[primbdtr][b][p][j]')
                            summgene(gdat.arrypcur['primbdtr'][b][p][j])
                            
                            raise Exception('')
                    
                        print('gdat.arrypcur[primbdtr][b][p][j]')
                        summgene(gdat.arrypcur['primbdtr'][b][p][j])
                        gdat.arrypcur['primbdtrbindtotl'][b][p][j] = ephesos.rebn_tser(gdat.arrypcur['primbdtr'][b][p][j], \
                                                                                                            binsxdat=gdat.binsphasprimtotl)
                        
                        if np.isfinite(gdat.duraprio[j]):
                            gdat.arrypcur['primbdtrbindzoom'][b][p][j] = ephesos.rebn_tser(gdat.arrypcur['primbdtr'][b][p][j], \
                                                                                                            binsxdat=gdat.binsphasprimzoom[j])
                        
                        gdat.arrypcur['quadbdtr'][b][p][j] = ephesos.fold_tser(gdat.arrytser['bdtr'][b][p][gdat.listindxtimeclen[j][b][p], :, :], \
                                                                                                gdat.epocmtracompprio[j], gdat.pericompprio[j], phasshft=0.25)
                        
                        gdat.arrypcur['quadbdtrbindtotl'][b][p][j] = ephesos.rebn_tser(gdat.arrypcur['quadbdtr'][b][p][j], \
                                                                                                            binsxdat=gdat.binsphasquadtotl)
                        
                        for e in gdat.indxener[p]:
                            path = gdat.pathdatatarg + 'arrypcurprimbdtrbind_%s_%s_%s.csv' % (gdat.liststrgener[p][e], gdat.liststrgcomp[j], gdat.liststrginst[b][p])
                            if not os.path.exists(path):
                                temp = np.copy(gdat.arrypcur['primbdtrbindtotl'][b][p][j][:, e, :])
                                temp[:, 0] *= gdat.pericompprio[j]
                                if gdat.typeverb > 0:
                                    print('Writing to %s...' % path)
                                np.savetxt(path, temp, delimiter=',', header='phase,%s,%s_err' % (gdat.liststrgtsercsvv[b], gdat.liststrgtsercsvv[b]))
                
            if gdat.boolplot:
                plot_pser(gdat, strgmodl, 'primbdtr')
    
    gdat.numbsamp = 10

    #if gdat.boolplotpopl:
    #    #for strgpdfn in gdat.liststrgpdfn:
    #    if gdat.typeverb > 0:
    #        print('Making plots highlighting the %s features of the target within its population...' % (strgpdfn))
    #    plot_popl(gdat, 'prio')
    #    #calc_feat(gdat, strgpdfn)
    
    if gdat.labltarg == 'WASP-121':
        # get Vivien's GCM model
        path = gdat.pathdatatarg + 'PC-Solar-NEW-OPA-TiO-LR.dat'
        arryvivi = np.loadtxt(path, delimiter=',')
        gdat.phasvivi = (arryvivi[:, 0] / 360. + 0.75) % 1. - 0.25
        gdat.deptvivi = arryvivi[:, 4]
        indxphasvivisort = np.argsort(gdat.phasvivi)
        gdat.phasvivi = gdat.phasvivi[indxphasvivisort]
        gdat.deptvivi = gdat.deptvivi[indxphasvivisort]
        path = gdat.pathdatatarg + 'PC-Solar-NEW-OPA-TiO-LR-AllK.dat'
        arryvivi = np.loadtxt(path, delimiter=',')
        gdat.wlenvivi = arryvivi[:, 1]
        gdat.specvivi = arryvivi[:, 2]
    
        ## TESS throughput 
        gdat.data = np.loadtxt(gdat.pathdatatarg + 'band.csv', delimiter=',', skiprows=9)
        gdat.meanwlenband = gdat.data[:, 0] * 1e-3
        gdat.thptband = gdat.data[:, 1]

    # do not continue if there is no trigger
    if gdat.booltserdata:
        
        # Boolean flag to continue modeling the data based on the feature extraction
        gdat.boolmodl = gdat.boolinfe and (gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'cosc' or gdat.fitt.typemodl == 'psyspcur') and \
                                                                               gdat.boolsrchpbox and not gdat.dictmileoutp['boolposianls'].any()
        
        if gdat.boolmodl:
            gdat.liststrgpdfn += ['post']

        if gdat.typeverb > 0:
            print('gdat.liststrgpdfn')
            print(gdat.liststrgpdfn)
    
        if not gdat.boolmodl:
            print('Skipping the forward modeling of this prior transiting object...')

    if gdat.booltserdata and gdat.boolmodl:
        
        # typemodlttvr
        # type of pipeline to fit transit times
        ## 'indilineuser': one fit for each transit, floating individual transits while fixing the orbital parameters including the
        ##                                                                              linear ephemerides (period and epoch) to user-defined values
        ## 'globlineuser': single fit across all transits with free transit times, but linear ephemerides from the user
        ## 'globlineflot': single fit across all transits with free transit times and linear ephemerides
        for strgmodl in gdat.liststrgmodl:
            gmod = getattr(gdat, strgmodl)
            if gmod.typemodl == 'psysttvr':
                tdpy.setp_para_defa(gdat, strgmodl, 'typemodlttvr', 'globlineflot')

        gdat.boolbrekmodl = False

        gdat.timethisfitt = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.rflxthisfitt = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]
        gdat.stdvrflxthisfitt = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]  
        gdat.varirflxthisfitt = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]  
        gdat.timethisfittfine = [[[] for p in gdat.indxinst[b]] for b in gdat.indxdatatser]  
        
        for b in gdat.indxdatatser:
            for p in gdat.indxinst[b]:
                if gdat.limttimefitt is None:
                    #if gdat.fitt.typemodl == 'supn':
                    #    indxtimetemp = np.argmin(abs(gdat.rflxthis[:, 0] - np.percentile(gdat.rflxthis, 1.) + \
                    #                                                            0.5 * (np.percentile(gdat.rflxthis, 99.) - np.percentile(gdat.rflxthis, 1.))))
                    #    indxtimefitt = np.where(gdat.timethis < gdat.timethis[indxtimetemp])[0]
                    #else:
                    indxtimefitt = np.arange(gdat.listarrytser['bdtr'][b][p][y].shape[0])
                else:
                    indxtimefitt = np.where((gdat.listarrytser['bdtr'][b][p][y][:, 0, 0] < gdat.limttimefitt[b][p][1]) & (gdat.timethis > gdat.limttimefitt[b][p][0]))[0]
                gdat.timethisfitt[b][p] = gdat.listarrytser['bdtr'][b][p][y][indxtimefitt, 0, 0]
                gdat.rflxthisfitt[b][p] = gdat.listarrytser['bdtr'][b][p][y][indxtimefitt, :, 1]
                gdat.stdvrflxthisfitt[b][p] = gdat.listarrytser['bdtr'][b][p][y][indxtimefitt, :, 2]
                
                # temp
                if np.amax(gdat.stdvrflxthisfitt[b][p]) > 10.:
                    print('gdat.timethisfitt[b][p]')
                    summgene(gdat.timethisfitt[b][p])
                    print('gdat.rflxthisfitt[b][p]')
                    summgene(gdat.rflxthisfitt[b][p])
                    print('gdat.stdvrflxthisfitt[b][p]')
                    summgene(gdat.stdvrflxthisfitt[b][p])
                    raise Exception('')

                gdat.varirflxthisfitt[b][p] = gdat.stdvrflxthisfitt[b][p]**2
                
                minmtimethisfitt = np.amin(gdat.timethisfitt[b][p])
                maxmtimethisfitt = np.amax(gdat.timethisfitt[b][p])
                difftimethisfittfine = 0.3 * np.amin(gdat.timethisfitt[b][p][1:] - gdat.timethisfitt[b][p][:-1])
                gdat.timethisfittfine[b][p] = np.arange(minmtimethisfitt, maxmtimethisfitt + difftimethisfittfine, difftimethisfittfine)
            
        gmod = gdat.fitt
        
        meangauspara = None
        stdvgauspara = None
        
        gdat.numbsampwalk = 10
        gdat.numbsampburnwalkinit = 0
        gdat.numbsampburnwalk = int(0.3 * gdat.numbsampwalk)
        
        #for b in gdat.indxdatatser:
        #    for p in gdat.indxinst[b]:
                
        if gdat.typeverb > 0:
            if gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'cosc' or gdat.fitt.typemodl == 'psyspcur':
                print('gdat.dictmileoutp[boolposianls]')
                print(gdat.dictmileoutp['boolposianls'])
            
        if gdat.typeverb > 0:
            print('gmod.typemodlblinshap')
            print(gmod.typemodlblinshap)
            print('gmod.typemodlblinener')
            print(gmod.typemodlblinener)
        
        # iterate over different subsets of data
        for e in gdat.indxdataiter:
        
            if gdat.typeinfe == 'opti':
                path = gdat.pathdatatarg + 'paramlik.csv'
                
                # temp
                if os.path.exists(path) and False:
                    print('Reading from %s...' % path)
                    objtfile = open(path, 'r')
                    gdat.liststrgdataitermlikdone = []
                    gdat.datamlik = []
                    for line in objtfile:
                        linesplt = line.split(',')
                        gdat.liststrgdataitermlikdone.append(linesplt[0]) 
                        gdat.datamlik.append(np.array(linesplt[1:]).astype(float))
                    objtfile.close()
                    gdat.liststrgdataitermlikdone = np.array(gdat.liststrgdataitermlikdone)
                else:
                    gdat.liststrgdataitermlikdone = np.array([])

            # Boolean flag indicating whether white light curve is modeled as opposed to spectral light curves
            if ee == 0:
                gdat.boolwhit = True
            else:
                gdat.boolwhit = False
            
            if gdat.typeverb > 0:
                print('')
                print('')
                print('gdat.indxdataiterthis')
                print(gdat.indxdataiterthis)
        
            if gdat.fitt.typemodl == 'supn':
                
                init_modl(gdat, 'fitt')

                gdat.minmtimethis = np.amin(gdat.timethis)
                gdat.maxmtimethis = np.amax(gdat.timethis)
                
                setp_modlbase(gdat, 'fitt', r)
        
                # define arrays of parameter indices
                #gmod.dictindxpara[namepara] = np.empty(2, dtype=int)
                
                strgextn = gdat.strgcnfg + gdat.fitt.typemodl
                proc_modl(gdat, 'fitt', strgextn, r)
                    
            elif gdat.fitt.typemodl == 'flar':

                init_modl(gdat, 'fitt')

                setp_modlbase(gdat, 'fitt', r)
        
                proc_modl(gdat, 'fitt', strgextn, r)


            elif gdat.fitt.typemodl == 'agns':

                init_modl(gdat, 'fitt')

                setp_modlbase(gdat, 'fitt', r)
        
                proc_modl(gdat, 'fitt', strgextn, r)


            elif gdat.fitt.typemodl == 'spot':

                # for each spot multiplicity, fit the spot model
                for gdat.numbspot in listindxnumbspot:
                    
                    init_modl(gdat, 'fitt')

                    setp_modlbase(gdat, 'fitt', r)
        
                    if gdat.typeverb > 0:
                        print('gdat.numbspot')
                        print(gdat.numbspot)

                    # list of parameter labels and units
                    gmod.listlablpara = [['$u_1$', ''], ['$u_2$', ''], ['$P$', 'days'], ['$i$', 'deg'], ['$\\rho$', ''], ['$C$', '']]
                    # list of parameter scalings
                    listscalpara = ['self', 'self', 'self', 'self', 'self', 'self']
                    # list of parameter minima
                    gmod.listminmpara = [-1., -1., 0.2,   0.,  0.,-1e-1]
                    # list of parameter maxima
                    gmod.listmaxmpara = [ 3.,  3., 0.4, 89.9, 0.6, 1e-1]
                    
                    for numbspottemp in range(gdat.numbspot):
                        gmod.listlablpara += [['$\\theta_{%d}$' % numbspottemp, 'deg'], \
                                                    ['$\\phi_{%d}$' % numbspottemp, 'deg'], ['$R_{%d}$' % numbspottemp, '']]
                        listscalpara += ['self', 'self', 'self']
                        gmod.listminmpara += [-90.,   0.,  0.]
                        gmod.listmaxmpara += [ 90., 360., 0.4]
                        if gdat.boolevol:
                            gmod.listlablpara += [['$T_{s;%d}$' % numbspottemp, 'day'], ['$\\sigma_{s;%d}$' % numbspottemp, '']]
                            listscalpara += ['self', 'self']
                            gmod.listminmpara += [gdat.minmtime, 0.1]
                            gmod.listmaxmpara += [gdat.maxmtime, 20.]
                            
                    # plot light curve
                    figr, axis = plt.subplots(figsize=(8, 4))
                    # plot samples from the posterior
                    ## the sample indices which will be plotted
                    indxsampplot = np.random.choice(gdat.indxsamp, size=gdat.numbsampplot, replace=False)
                    indxsampplot = np.sort(indxsampplot)
                    listlcurmodl = np.empty((gdat.numbsampplot, gdat.numbtime))
                    listlcurmodlevol = np.empty((gdat.numbsampplot, gdat.numbspot, gdat.numbtime))
                    listlcurmodlspot = np.empty((gdat.numbsampplot, gdat.numbspot, gdat.numbtime))
                    for kk, k in enumerate(indxsampplot):
                        # calculate the model light curve for this parameter vector
                        listlcurmodl[kk, :], listlcurmodlevol[kk, :, :], listlcurmodlspot[kk, :, :] = ephesos.retr_rflxmodl(gdat, listpost[k, :])
                        axis.plot(gdat.time, listlcurmodl[kk, :], color='b', alpha=0.1)
                    
                    # plot components of each sample
                    for kk, k in enumerate(indxsampplot):
                        dictpara = pars_para(gdat, listpost[k, :])
                        plot_totl(gdat, k, listlcurmodl[kk, :], listlcurmodlevol[kk, :, :], listlcurmodlspot[kk, :, :], dictpara)

                    # plot map
                    figr, axis = plt.subplots(figsize=(8, 4))
                    gdat.numbside = 2**10
                    
                    lati = np.empty((gdat.numbsamp, gdat.numbspot))
                    lngi = np.empty((gdat.numbsamp, gdat.numbspot))
                    rrat = np.empty((gdat.numbsamp, gdat.numbspot))
                    for n in gdat.indxsamp:
                        dictpara = pars_para(gdat, listpost[n, :])
                        lati[n, :] = dictpara['lati']
                        lngi[n, :] = dictpara['lngi']
                        rrat[n, :] = dictpara['rratcomp']
                    lati = np.median(lati, 0)
                    lngi = np.median(lngi, 0)
                    rrat = np.median(rrat, 0)

                    plot_moll(gdat, lati, lngi, rrat)
                    
                    #for k in indxsampplot:
                    #    lati = listpost[k, 1+0*gdat.numbparaspot+0]
                    #    lngi = listpost[k, 1+0*gdat.numbparaspot+1]
                    #    rrat = listpost[k, 1+0*gdat.numbparaspot+2]
                    #    plot_moll(gdat, lati, lngi, rrat)

                    for sp in ['right', 'top']:
                        axis.spines[sp].set_visible(False)

                    path = gdat.pathvisutarg + 'smap%s_ns%02d.%s' % (strgtarg, gdat.numbspot, gdat.typefileplot)
                    gdat.listdictdvrp[j+1].append({'path': path, 'limt':[0., 0.05, 1., 0.1]})
                    if gdat.typeverb > 0:
                        print('Writing to %s...' % path)
                    plt.savefig(path)
                    plt.close()


            elif gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'cosc' or gdat.fitt.typemodl == 'psyspcur' or gdat.fitt.typemodl == 'psysttvr':
                
                if gdat.fitt.typemodl == 'psysttvr':
                    if gdat.fitt.typemodlttvr == 'indilineuser':
                        gdat.numbiterfitt = gdat.numbtran
                    elif gdat.fitt.typemodlttvr == 'globlineuser':
                        gdat.numbiterfitt = 1
                    elif gdat.fitt.typemodlttvr == 'globlineflot':
                        gdat.numbiterfitt = 1
                else:
                    gdat.numbiterfitt = 1
                
                gdat.indxiterfitt = np.arange(gdat.numbiterfitt)
                
                for ll in gdat.indxiterfitt:
                    
                    init_modl(gdat, 'fitt')

                    setp_modlbase(gdat, 'fitt', r)
                    
                    strgextn = gdat.strgcnfg + gdat.fitt.typemodl
                    if gdat.fitt.typemodlenerfitt == 'iter':
                        strgextn += gdat.liststrgdataiter[gdat.indxdataiterthis[0]]
                    proc_modl(gdat, 'fitt', strgextn, r)

            elif gdat.fitt.typemodl == 'stargpro':
                
                init_modl(gdat, 'fitt')

                setp_modlbase(gdat, 'fitt', r)
        
                pass
            else:
                print('')
                print('A model type was not defined.')
                print('gdat.fitt.typemodl')
                print(gdat.fitt.typemodl)
                raise Exception('')
        
        if gdat.typeinfe == 'samp':
            gdat.indxsampmpos = np.argmax(gdat.dictsamp['lpos'])
            
            gdat.indxsampplot = np.random.choice(gdat.indxsamp, gdat.numbsampplot, replace=False)

            if gdat.typeverb > 0:
                print('gdat.numbsamp')
                print(gdat.numbsamp)
                print('gdat.numbsampplot')
                print(gdat.numbsampplot)
        
        if gdat.numbener[p] > 1 and (gdat.fitt.typemodl == 'psys' or gdat.fitt.typemodl == 'cosc' or gdat.fitt.typemodl == 'psyspcur'):
            # plot the radius ratio spectrum
            path = gdat.pathvisutarg + 'spec%s.%s' % (gdat.strgcnfg, gdat.typefileplot)
            figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
            pmedrratcompspec = np.empty(gdat.numbener[p])
            perrrratcompspec = np.empty(gdat.numbener[p])
            for e in gdat.indxener[p]:
                if gdat.typeinfe == 'samp':
                    if gdat.fitt.typemodlenerfitt == 'full':
                        listrratcomp = gdat.dictsamp['rratcomp' + gdat.liststrgener[p][e]]
                    else:
                        listrratcomp = gmod.listdictsamp[e+1]['rratcomp' + gdat.liststrgener[p][e]]
                    pmedrratcompspec[e] = np.median(listrratcomp)
                    perrrratcompspec[e] = (np.percentile(listrratcomp, 86.) - np.percentile(listrratcomp, 14.)) / 2.
                else:
                    if gdat.fitt.typemodlenerfitt == 'full':
                        pmedrratcompspec[e] = gdat.dictmlik['rratcomp' + gdat.liststrgener[p][e]]
                    else:
                        pmedrratcompspec[e] = gmod.listdictmlik[e+1]['rratcomp' + gdat.liststrgener[p][e]]
                        perrrratcompspec[e] = gmod.listdictmlik[e+1]['stdvrratcomp' + gdat.liststrgener[p][e]]
            axis.plot(gdat.listener[p], pmedrratcompspec, ls='', marker='o')
            # plot binned spectrum
            #    arry = np.zeros((dictvarbderi['rflxresi'][:, e].size, 3))
            #    arry[:, 0] = gdat.timethisfitt
            #    arry[:, 1] = dictvarbderi['rflxresi'][:, e]
            #    stdvrflxresi = np.nanstd(ephesos.rebn_tser(arry, delt=gdat.listdeltrebn[b][p])[:, 1])
            axis.plot(gdat.listener[p], pmedrratcompspec, ls='', marker='o')
            axis.set_ylabel('$R_p/R_*$')
            axis.set_xlabel('Wavelength [$\mu$m]')
            plt.tight_layout()
            if gdat.typeverb > 0:
                print('Writing to %s...' % path)
            plt.savefig(path)
            plt.close()
            
            # load the spectrum to the output dictionary
            gdat.dictmileoutp['pmedrratcompspec'] = pmedrratcompspec
            gdat.dictmileoutp['perrrratcompspec'] = perrrratcompspec

            #path = gdat.pathvisutarg + 'stdvrebnener%s.%s' % (gdat.strgcnfg, gdat.typefileplot)
            #if not os.path.exists(path):
            #    figr, axis = plt.subplots(figsize=gdat.figrsizeydob)
            #    arry = np.zeros((dictvarbderi['rflxresi'][:, e].size, 3))
            #    arry[:, 0] = gdat.timethisfitt
            #    arry[:, 1] = dictvarbderi['rflxresi'][:, e]
            #    for k in gdat.indxrebn:
            #    stdvrflxresi = np.nanstd(ephesos.rebn_tser(arry, delt=gdat.listdeltrebn[b][p])[:, 1])
            #    axis.loglog(gdat.listdeltrebn[b][p], stdvrflxresi * 1e6, ls='', marker='o', ms=1, label='Binned Std. Dev')
            #    axis.axvline(gdat.ratesampener, ls='--', label='Sampling rate')
            #    axis.axvline(gdat.enerscalbdtr, ls='--', label='Detrending scale')
            #    axis.set_ylabel('RMS [ppm]')
            #    axis.set_xlabel('Bin width [$\mu$m]')
            #    axis.legend()
            #    plt.tight_layout()
            #    if gdat.typeverb > 0:
            #        print('Writing to %s...' % path)
            #    plt.savefig(path)
            #    plt.close()


    path = gdat.pathdatatarg + 'dictmileoutp.pickle'
    if gdat.typeverb > 0:
        print('Writing to %s...' % path)
    
    # to be deleted
    #with open(path, 'wb') as objthand:
    #    pickle.dump(gdat.dictmileoutp, objthand)
    
    if gdat.booltserdata and gdat.boolplot and gdat.boolplotdvrp:
        listpathdvrp = []
        # make data-validation report
        for w in gdat.indxpage:
            # path of DV report
            pathplot = gdat.pathvisutarg + '%s_dvrp_pag%d.png' % (gdat.strgtarg, w + 1)
            listpathdvrp.append(pathplot)
            
            if not os.path.exists(pathplot):
                # create page with A4 size
                figr = plt.figure(figsize=(8.25, 11.75))
                
                numbplot = len(gdat.listdictdvrp[w])
                indxplot = np.arange(numbplot)
                for dictdvrp in gdat.listdictdvrp[w]:
                    axis = figr.add_axes(dictdvrp['limt'])
                    axis.imshow(plt.imread(dictdvrp['path']))
                    axis.axis('off')
                if gdat.typeverb > 0:
                    print('Writing to %s...' % pathplot)
                plt.savefig(pathplot, dpi=600)
                #plt.subplots_adjust(top=1., bottom=0, left=0, right=1)
                plt.close()
        
        gdat.dictmileoutp['listpathdvrp'] = listpathdvrp

    # write the output dictionary to target file
    path = gdat.pathdatatarg + 'mileoutp.csv'
    objtfile = open(path, 'w')
    k = 0
    for name, valu in gdat.dictmileoutp.items():
        if isinstance(valu, str) or isinstance(valu, float) or isinstance(valu, int) or isinstance(valu, bool):
            objtfile.write('%s, ' % name)
        if isinstance(valu, str):
            objtfile.write('%s' % valu)
        elif isinstance(valu, float) or isinstance(valu, int) or isinstance(valu, bool):
            objtfile.write('%g' % valu)
        if isinstance(valu, str) or isinstance(valu, float) or isinstance(valu, int) or isinstance(valu, bool):
            objtfile.write('\n')
    if typeverb > 0:
        print('Writing to %s...' % path)
    objtfile.close()
    
    # write the output dictionary to the cluster file
    if gdat.strgclus is not None:
        path = gdat.pathdataclus + 'mileoutp.csv'
        boolappe = True
        if os.path.exists(path):
            print('Reading from %s...' % path)
            dicttemp = pd.read_csv(path).to_dict(orient='list')
            if gdat.strgtarg in dicttemp['strgtarg']:
                boolappe = False
            boolmakehead = False
        else:
            print('Opening %s...' % path)
            objtfile = open(path, 'w')
            boolmakehead = True
        
        if boolappe:
            
            print('gdat.dictmileoutp')
            for name in gdat.dictmileoutp:
                if 'path' in name:
                    print(name)

            if boolmakehead:
                print('Constructing the header...')
                # if the header doesn't exist, make it
                k = 0
                listnamecols = []
                for name, valu in gdat.dictmileoutp.items():
                    
                    if name.startswith('lygo_pathsaverflx'): 
                        continue
                    
                    if name.startswith('lygo_strgtitlcntpplot'):
                        continue
                    
                    listnamecols.append(name)
                    if isinstance(valu, str) or isinstance(valu, float) or isinstance(valu, int) or isinstance(valu, bool):
                        if k > 0:
                            objtfile.write(',')
                        objtfile.write('%s' % name)
                        k += 1
                
            else:
                print('Reading from %s...' % path)
                objtfile = open(path, 'r')
                for line in objtfile:
                    listnamecols = line.split(',')
                    break
                listnamecols[-1] = listnamecols[-1][:-1]

                if not gdat.strgtarg in dicttemp['strgtarg']:
                    print('Opening %s to append...' % path)
                    objtfile = open(path, 'a')
            
            objtfile.write('\n')
            k = 0
            
            print('listnamecols')
            for name in listnamecols:
                if 'path' in name:
                    print(name)
            
            for name in listnamecols:
                valu = gdat.dictmileoutp[name]
                if isinstance(valu, str) or isinstance(valu, float) or isinstance(valu, int) or isinstance(valu, bool):
                    if k > 0:
                        objtfile.write(',')
                    if isinstance(valu, str):
                        objtfile.write('%s' % valu)
                    elif isinstance(valu, float) or isinstance(valu, int) or isinstance(valu, bool):
                        objtfile.write('%g' % valu)
                    k += 1
            #objtfile.write('\n')
            if typeverb > 0:
                print('Writing to %s...' % path)
            objtfile.close()

    # measure final time
    gdat.timefinl = modutime.time()
    gdat.timeexec = gdat.timefinl - gdat.timeinit
    if gdat.typeverb > 0:
        print('miletos ran in %.3g seconds.' % gdat.timeexec)
        print('')
        print('')
        print('')
    
    #'lygo_meannois', 'lygo_medinois', 'lygo_stdvnois', \
    for name in ['strgtarg', 'pathtarg', 'timeexec']:
        gdat.dictmileoutp[name] = getattr(gdat, name)

    return gdat.dictmileoutp


